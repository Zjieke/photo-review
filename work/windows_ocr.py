"""Offline OCR provided by Windows, using installed language packs only."""
import asyncio


async def _read(path):
    from winrt.windows.storage import StorageFile, FileAccessMode
    from winrt.windows.graphics.imaging import BitmapDecoder, BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    file = await StorageFile.get_file_from_path_async(str(path.resolve()))
    stream = await file.open_async(FileAccessMode.READ)
    try:
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        try:
            converted = SoftwareBitmap.convert(bitmap, BitmapPixelFormat.BGRA8)
            try:
                engine = OcrEngine.try_create_from_user_profile_languages()
                if engine is None:
                    return '', 'language_unavailable'
                result = await engine.recognize_async(converted)
                return result.text, 'complete'
            finally:
                converted.close()
        finally:
            bitmap.close()
    finally:
        stream.close()


def recognize(path):
    try:
        return asyncio.run(_read(path))
    except Exception:
        # A missing language pack must not prevent folder inventory and thumbnails.
        return '', 'unavailable'
