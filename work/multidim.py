"""Additive dimensions with explicit rule/model provenance and no automatic disposal decisions."""
from collections import OrderedDict
DIMENSIONS = OrderedDict([
 ('type',('图片类型',['截屏','聊天截图','长截图','实拍照片','文档图片','界面截图','普通图片','类型待确认'])),
 ('topic',('内容主题',['游戏','购物','餐饮','出行','社交聊天','工作开发','学习资料','生活记录','人物合影','自然风景','动物植物','医疗健康','金融支付','证件账户','其它内容','主题待确认'])),
 ('platform',('平台 / 游戏',['微信','QQ','小红书','微博','抖音','快手','哔哩哔哩','淘宝','天猫','京东','拼多多','闲鱼','唯品会','得物','美团','饿了么','瑞幸','支付宝','银行','携程','12306','王者荣耀','和平精英','原神','金铲铲之战','英雄联盟','冒险岛','其它游戏','平台待确认'])),
 ('content',('具体内容',['游戏过程','战绩结算','游戏活动','游戏攻略','聊天对话','聊天列表','朋友圈','商品详情','商品列表','购物车','订单详情','物流取件','退款售后','优惠促销','支付转账','账单发票','取餐码','二维码','菜单点单','票务行程','地图导航','代码报错','教程笔记','表格文档','体检病历','证件信息','人物','儿童','美食','风景','宠物','花草','活动海报','网页文章','内容待确认'])),
 ('quality',('识别来源',['看图试跑','文字与基础识别','疑似相似图片','含重要资料','已收藏','已隐藏']))
])
DIMENSIONS['platform'][1].extend(['苹果系统','高德地图','百度地图','百度','优酷','腾讯视频','虎扑','豆瓣','钉钉','企业微信','网易云音乐','苏宁易购','招商银行','微信读书','store by .jpg','知乎','小米汽车'])
DIMENSIONS['topic'][1].extend(['运动健身','娱乐影音','交通车辆','家居生活','数码设备'])
DIMENSIONS['content'][1].extend(['游戏组队','游戏报告','游戏排行','游戏提示','游戏大厅','通知消息','设置页面','存储空间','联系人列表','应用列表','表情包','手机桌面','服饰鞋包','数码产品','食品饮品','车辆','家居用品','影视画面','视频播放','运动记录','天气','音乐播放','订阅服务','搜索结果','商品评价','银行卡片','录音语音','账号信息','优惠券','文章资讯','导航路线','健身计划','软件功能','活动报名','软件提示','游戏社区','商品参数','订单列表','客服对话','运动用品','家电','看房视频','财务通知','工作台','营销广告','汽车服务','锁屏界面','充电服务','商品包装','充值服务','探店攻略','年度报告','门锁记录','评论区','游戏角色','游戏背包','考勤打卡','演出票务','智能家居','清扫地图','行车数据','车辆控制','维修服务','车辆定位','AI对话','文件列表','电子书','理财收益','AI相关','婚礼活动','软件下载','游乐活动','游泳','房产宣传','烟花','交通标识','房屋装修','短信通知','交通通知','车辆细节','宴席菜单','演唱会现场','街景','餐饮小票','电影票','设备面板','自拍合影','羽毛球','运动场馆','户外活动'])

DIMENSIONS['topic'][1].extend(['文档资料'])
DIMENSIONS['content'][1].extend(['动物','建筑空间','插画图案','文字图片'])
DIMENSIONS['quality'][1].extend(['本机画面识别','相似样本推断','待完成看图','识别失败','本地视觉模型','本地模型待确认'])

PLATFORMS={'微信':['微信','wechat'],'QQ':['qq'],'小红书':['小红书'],'微博':['微博'],'抖音':['抖音'],'快手':['快手'],'哔哩哔哩':['哔哩哔哩','bilibili'],'淘宝':['淘宝','taobao'],'天猫':['天猫','tmall'],'京东':['京东','京東','jd.com'],'拼多多':['拼多多'],'闲鱼':['闲鱼'],'唯品会':['唯品会'],'得物':['得物'],'美团':['美团'],'饿了么':['饿了么'],'瑞幸':['瑞幸','luckin'],'支付宝':['支付宝'],'携程':['携程'],'12306':['12306'],'王者荣耀':['王者荣耀','王者营地','巅峰赛','荣耀战力'],'和平精英':['和平精英'],'原神':['原神'],'金铲铲之战':['金铲铲'],'英雄联盟':['英雄联盟']}
CONTENT={'订单详情':['订单编号','订单号','订单详情','待收货','确认收货'],'物流取件':['取件码','快递单号','物流详情','菜鸟驿站'],'退款售后':['申请退款','退款详情','退款成功','售后详情','退货退款'],'商品详情':['商品详情','加入购物车','立即购买','商品参数','商品评价'],'商品列表':['综合排序','销量排序'],'购物车':['购物车','去结算'],'优惠促销':['优惠券','满减','限时优惠','秒杀'],'支付转账':['支付成功','付款成功','转账成功','交易单号'],'账单发票':['发票','账单详情'],'取餐码':['取餐码','取单码','核销码'],'二维码':['二维码','扫一扫','扫码'],'菜单点单':['立即下单','加入餐车','规格选择'],'票务行程':['登机牌','车次','航班','电子客票'],'地图导航':['开始导航','驾车路线'],'代码报错':['traceback','exception','stacktrace'],'教程笔记':['教程','知识点','学习资料','课程表'],'体检病历':['检验报告','处方','病历','诊断'],'证件信息':['身份证','护照','恢复码','银行卡'],'聊天对话':['拍了拍','撤回了一条消息','以下为新消息'],'聊天列表':['文件传输助手','订阅号消息'],'朋友圈':['朋友圈','朋友仅展示最近'],'战绩结算':['战绩','荣耀战力','助攻','击杀'],'游戏活动':['赛季奖励','战令','皮肤碎片']}
CONTENT_TOPICS={'购物':{'商品详情','商品列表','购物车','订单详情','物流取件','退款售后'},'餐饮':{'取餐码','菜单点单'},'游戏':{'战绩结算','游戏过程','游戏活动','游戏攻略'},'社交聊天':{'聊天对话','聊天列表','朋友圈'},'金融支付':{'支付转账','账单发票'},'医疗健康':{'体检病历'},'证件账户':{'证件信息'},'出行':{'票务行程','地图导航'},'工作开发':{'代码报错'},'学习资料':{'教程笔记','表格文档'}}

def infer(row, vlm=None):
 text=''.join(row.get('ocr','').lower().split())
 evidence={};d={k:[] for k in DIMENSIONS}
 d['type']=['截屏'] if row.get('screenshot') else ['普通图片']
 from PIL import Image
 try:
  with Image.open(row['preview_for_dimensions']) as im:
   if im.height/im.width>3.0:d['type'].append('长截图')
 except Exception:pass
 for tag,words in PLATFORMS.items():
  hits=[w for w in words if w in text]
  if hits:d['platform'].append(tag);evidence[tag]=['文字线索：'+ '、'.join(hits)]
 for tag,words in CONTENT.items():
  hits=[w for w in words if w in text]
  if hits:d['content'].append(tag);evidence[tag]=['文字线索：'+ '、'.join(hits)]
 for topic,contents in CONTENT_TOPICS.items():
  if set(d['content'])&contents:d['topic'].append(topic)
 if row.get('qr_detected') and '二维码' not in d['content']:d['content'].append('二维码');evidence['二维码']=['本地图像检测到二维码']
 if any(x in d['content'] for x in ['聊天对话','聊天列表','朋友圈']):d['type']=['截屏','聊天截图']+(['长截图'] if '长截图' in d['type'] else [])
 visuals={v['label'] for v in row.get('visual',[]) if v['confidence']>=0.75}
 if not row.get('screenshot'):
  for label,vs,topic in [('人物',{'people','adult','crowd'},'人物合影'),('儿童',{'baby','toddler','child'},'生活记录'),('美食',{'food','meal','dessert'},'生活记录'),('风景',{'landscape','mountain','beach'},'自然风景'),('宠物',{'dog','cat','pet'},'动物植物'),('花草',{'flower','plant'},'动物植物')]:
   if visuals&vs:
    d['content'].append(label);d['topic'].append(topic);evidence[label]=['Apple Vision 基础画面分类建议']
 if vlm and vlm.get('status')=='complete':
  evidence=vlm.get('evidence') or {'画面依据':[vlm.get('reason','未提供画面描述')],'识别方式':['本次助手查看样本画面，并参考可见文字线索；不是本地模型输出']}
  for k in ('type','topic','platform','content'):
   values=[v for v in vlm.get(k,[]) if v in DIMENSIONS[k][1]]
   d[k]=values
   # Keep a single visual rationale instead of repeating it for every label.
  if row.get('screenshot') and '截屏' not in d['type']:d['type'].insert(0,'截屏')
  if row.get('qr_detected') and '二维码' not in d['content']:d['content'].append('二维码');evidence['二维码']=['本地图像检测到二维码']
  if vlm.get('model')=='apple-vision-reference-classifier':
   d['quality'].append('本机画面识别')
   if vlm.get('reference_used'):d['quality'].append('相似样本推断')
  elif vlm.get('model','').startswith('Qwen3.5'):
   d['quality'].append('本地视觉模型')
   if vlm.get('uncertain'):d['quality'].append('本地模型待确认')
  else:d['quality'].append('看图试跑')
 else:d['quality'].append('文字与基础识别')
 if row.get('analysis_status') in ('failed','unavailable'):d['quality'].append('识别失败')
 if set(d['content'])&{'订单详情','支付转账','账单发票','体检病历','证件信息'}:d['quality'].append('含重要资料')
 if row.get('favorite'):d['quality'].append('已收藏')
 if row.get('hidden'):d['quality'].append('已隐藏')
 for k,fallback in [('type','类型待确认'),('topic','主题待确认'),('content','内容待确认')]:
  if not d[k]:d[k]=[fallback]
 return {k:list(dict.fromkeys(v)) for k,v in d.items()},evidence
