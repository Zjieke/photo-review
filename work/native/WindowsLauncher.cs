// A launch carrier only: all product interactions stay in the user's browser.
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

class PhotoReview {
    [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
        public long ProcessTime, JobTime; public uint Flags;
        public UIntPtr MinWorking, MaxWorking; public uint ActiveProcesses;
        public UIntPtr Affinity; public uint Priority, Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] struct IoCounters {
        public ulong ReadOperations, WriteOperations, OtherOperations, ReadBytes, WriteBytes, OtherBytes;
    }
    [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {
        public BasicLimits Basic; public IoCounters Io;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll")] static extern bool SetInformationJobObject(IntPtr job, int infoClass, ref ExtendedLimits info, uint size);
    [DllImport("kernel32.dll")] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);

    [STAThread] static int Main(string[] args) {
        Application.EnableVisualStyles();
        if (args.Length == 2 && args[0] == "--pick-folder") {
            using (var picker = new FolderBrowserDialog()) {
                picker.Description = "选择存放照片和视频的文件夹（云盘照片请先下载到本机）";
                picker.ShowNewFolderButton = false;
                if (picker.ShowDialog() == DialogResult.OK) {
                    // Only the child writes this response; no shell or user-provided code.
                    string escaped = picker.SelectedPath.Replace("\\", "\\\\").Replace("\"", "\\\"");
                    File.WriteAllText(args[1], "{\"folder\":\"" + escaped + "\"}", new UTF8Encoding(false));
                }
            }
            return 0;
        }
        string app = AppDomain.CurrentDomain.BaseDirectory;
        string data = Environment.GetEnvironmentVariable("PHOTO_REVIEW_DATA_DIR");
        if (String.IsNullOrWhiteSpace(data)) data = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Photo Review");
        Directory.CreateDirectory(Path.Combine(data, "logs"));
        string logPath = Path.Combine(data, "logs", "launcher.log");
        IntPtr job = IntPtr.Zero;
        try {
            var info = new ProcessStartInfo(Path.Combine(app, "runtime", "pythonw.exe"),
                "-X utf8 -u \"" + Path.Combine(app, "project", "launcher.py") + "\" --packaged");
            info.WorkingDirectory = app; info.UseShellExecute = false; info.CreateNoWindow = true;
            info.RedirectStandardOutput = true; info.RedirectStandardError = true;
            info.StandardOutputEncoding = Encoding.UTF8; info.StandardErrorEncoding = Encoding.UTF8;
            info.EnvironmentVariables.Remove("PYTHONHOME"); info.EnvironmentVariables.Remove("PYTHONPATH");
            info.EnvironmentVariables["PYTHONUTF8"] = "1";
            info.EnvironmentVariables["PHOTO_REVIEW_DATA_DIR"] = data;
            info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
            info.EnvironmentVariables["PYTHONNOUSERSITE"] = "1";
            using (var output = new StreamWriter(new FileStream(logPath, FileMode.Append, FileAccess.Write, FileShare.ReadWrite), new UTF8Encoding(false)))
            using (var process = new Process()) {
                object sync = new object(); output.AutoFlush = true;
                process.StartInfo = info;
                DataReceivedEventHandler receive = (sender, e) => { if (e.Data != null) lock(sync) output.WriteLine(e.Data); };
                process.OutputDataReceived += receive; process.ErrorDataReceived += receive;
                process.Start();
                job = CreateJobObject(IntPtr.Zero, null);
                var limits = new ExtendedLimits(); limits.Basic.Flags = 0x2000; // KILL_ON_JOB_CLOSE
                if (job == IntPtr.Zero || !SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf(limits)) ||
                    !AssignProcessToJobObject(job, process.Handle)) {
                    process.Kill(); throw new Exception("无法创建后台任务容器，请重新启动程序。");
                }
                process.BeginOutputReadLine(); process.BeginErrorReadLine(); process.WaitForExit();
                if (process.ExitCode != 0 && Environment.GetEnvironmentVariable("PHOTO_REVIEW_NO_BROWSER") != "1")
                    MessageBox.Show("程序启动或运行未完成。日志位置：\n" + logPath, "照片整理", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return process.ExitCode;
            }
        } catch (Exception error) {
            File.AppendAllText(logPath, error.ToString() + Environment.NewLine, Encoding.UTF8);
            if (Environment.GetEnvironmentVariable("PHOTO_REVIEW_NO_BROWSER") != "1")
                MessageBox.Show("无法启动照片整理。请完整解压下载包后再双击程序。\n日志：" + logPath, "照片整理", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        } finally { if (job != IntPtr.Zero) CloseHandle(job); }
    }
}
