import ntplib
import datetime
import pytz
import time

class TimeService:
    def __init__(self, ap):
        self.ap = ap
        self.ntp_server = "ntp.aliyun.com"
        self.timezone = "Asia/Shanghai"  # 默认时区
        self.use_ntp_time = True  # 默认启用NTP时间
        self.last_sync_time = 0
        self.time_offset = 0  # 本地时间与NTP时间的偏移量
        self.sync_interval = 3600  # 同步间隔，默认1小时

    async def load_config(self, config_data):
        """从配置中加载时区和NTP开关设置"""
        self.timezone = config_data.get("timezone", "Asia/Shanghai")
        self.use_ntp_time = config_data.get("use_ntp_time", True)
        self.ntp_server = config_data.get("ntp_server", "ntp.aliyun.com")
        self.sync_interval = config_data.get("ntp_sync_interval", 3600)

    async def sync_time(self):
        """与NTP服务器同步时间"""
        if not self.use_ntp_time:
            return
            
        # 检查是否需要同步（避免频繁同步）
        current_time = time.time()
        if current_time - self.last_sync_time < self.sync_interval:
            return
            
        try:
            client = ntplib.NTPClient()
            response = client.request(self.ntp_server, timeout=5)
            self.time_offset = response.offset
            self.last_sync_time = current_time
            self.ap.logger.info(f"成功与NTP服务器{self.ntp_server}同步时间，偏移量：{self.time_offset}秒")
        except Exception as e:
            self.ap.logger.error(f"NTP时间同步失败: {str(e)}")

    def get_current_time(self):
        """获取当前时间，如果启用了NTP，则使用校正后的时间"""
        if self.use_ntp_time:
            # 使用本地时间加上偏移量
            current_time = time.time() + self.time_offset
        else:
            current_time = time.time()
            
        # 转换为datetime对象
        dt = datetime.datetime.fromtimestamp(current_time)
        
        # 设置时区
        try:
            tz = pytz.timezone(self.timezone)
            dt = dt.astimezone(tz)
        except Exception as e:
            self.ap.logger.error(f"时区设置失败: {str(e)}，使用系统默认时区")
            
        return dt
    
    def get_formatted_time(self, format_str="%Y年%m月%d日%H时%M分"):
        """获取格式化的时间字符串"""
        dt = self.get_current_time()
        return dt.strftime(format_str)
    
    def get_time_context(self):
        """获取用于发送给大模型的时间上下文"""
        if not self.use_ntp_time:
            return ""
            
        dt = self.get_current_time()
        formatted_time = self.get_formatted_time()
        
        # 构建时间上下文
        time_context = f"当前时间是{formatted_time}。"
        
        return time_context