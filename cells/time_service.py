import socket
import struct
import time
import datetime
import pytz
from pkg.core import app
from plugins.Waifu.cells.config import ConfigManager


class TimeService:
    """
    时间服务类，用于获取NTP服务器时间并进行时区转换
    """
    # NTP服务器的默认端口
    NTP_PORT = 123
    # NTP时间与Unix时间的偏移量（1900年到1970年的秒数）
    NTP_DELTA = 2208988800
    
    ap: app.Application
    
    def __init__(self, ap: app.Application):
        self.ap = ap
        self.ntp_server = "ntp.aliyun.com"
        self.timezone = "Asia/Shanghai"
        self.enabled = True
        self.include_date = True
        self.include_time = True
        self.include_timezone = True
        self.format_str = "%Y年%m月%d日%H时%M分"
        self.last_sync_time = 0
        self.time_offset = 0  # 本地时间与NTP时间的偏移量
        self.sync_interval = 3600  # 默认每小时同步一次NTP时间
    
    async def load_config(self, launcher_id: str):
        """
        从配置文件加载时间服务配置
        """
        config_mgr = ConfigManager(f"data/plugins/Waifu/config/waifu", "plugins/Waifu/templates/waifu", launcher_id)
        await config_mgr.load_config(completion=True)
        
        # 加载时间服务配置
        time_service_config = config_mgr.data.get("time_service", {})
        self.enabled = time_service_config.get("enabled", True)
        self.ntp_server = time_service_config.get("ntp_server", "ntp.aliyun.com")
        self.timezone = time_service_config.get("timezone", "Asia/Shanghai")
        self.include_date = time_service_config.get("include_date", True)
        self.include_time = time_service_config.get("include_time", True)
        self.include_timezone = time_service_config.get("include_timezone", False)
        self.sync_interval = time_service_config.get("sync_interval", 3600)
        
        # 根据配置生成时间格式字符串
        self._generate_format_string()
        
        # 初始同步时间
        if self.enabled:
            await self.sync_time()
    
    def _generate_format_string(self):
        """
        根据配置生成时间格式字符串
        """
        format_parts = []
        if self.include_date:
            format_parts.append("%Y年%m月%d日")
        if self.include_time:
            format_parts.append("%H时%M分")
        
        self.format_str = "".join(format_parts)
    
    async def sync_time(self):
        """
        与NTP服务器同步时间
        """
        try:
            # 检查是否需要同步（避免频繁同步）
            current_time = time.time()
            if current_time - self.last_sync_time < self.sync_interval:
                return
            
            # 创建UDP套接字
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(5.0)  # 设置超时时间为5秒
            
            # 准备NTP请求数据包
            # 第一个字节: 00 = 闰秒指示器关闭, 011 = 版本号3, 011 = 客户端模式
            # 其余字节设置为0
            data = b'\x1b' + 47 * b'\0'
            
            # 发送请求到NTP服务器
            client.sendto(data, (self.ntp_server, self.NTP_PORT))
            
            # 接收响应
            data, address = client.recvfrom(1024)
            
            # 关闭套接字
            client.close()
            
            # 解析时间戳（位于接收数据的第40-43字节）
            t = struct.unpack('!12I', data)[10]
            t -= self.NTP_DELTA
            
            # 计算本地时间与NTP时间的偏移量
            self.time_offset = t - time.time()
            self.last_sync_time = current_time
            
            self.ap.logger.info(f"成功与NTP服务器{self.ntp_server}同步时间，偏移量: {self.time_offset}秒")
            return True
        except Exception as e:
            self.ap.logger.error(f"NTP时间同步失败: {str(e)}")
            return False
    
    def get_current_time(self) -> datetime.datetime:
        """
        获取当前时间（考虑NTP偏移）
        """
        # 获取当前时间并应用NTP偏移
        current_time = time.time() + self.time_offset
        # 转换为datetime对象
        dt = datetime.datetime.fromtimestamp(current_time)
        # 应用时区
        if self.timezone:
            try:
                tz = pytz.timezone(self.timezone)
                dt = dt.replace(tzinfo=pytz.UTC).astimezone(tz)
            except Exception as e:
                self.ap.logger.error(f"时区转换失败: {str(e)}")
        
        return dt
    
    def format_time(self, dt: datetime.datetime = None) -> str:
        """
        格式化时间为指定格式
        """
        if dt is None:
            dt = self.get_current_time()
        
        formatted_time = dt.strftime(self.format_str)
        
        # 如果需要添加时区信息
        if self.include_timezone and dt.tzinfo:
            tz_name = dt.tzinfo.tzname(dt)
            formatted_time = f"{formatted_time} ({tz_name})"
        
        return formatted_time
    
    def get_formatted_current_time(self) -> str:
        """
        获取格式化的当前时间字符串
        """
        if not self.enabled:
            return ""
        
        return self.format_time()
    
    def get_time_context(self) -> str:
        """
        获取用于发送给大模型的时间上下文信息
        """
        if not self.enabled:
            return ""
        
        current_time = self.get_current_time()
        formatted_time = self.format_time(current_time)
        
        # 构建时间上下文
        context = f"当前时间是{formatted_time}。"
        
        # 添加一些时间相关的上下文信息
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekday_names[current_time.weekday()]
        context += f"今天是{weekday}。"
        
        # 判断是上午还是下午
        if current_time.hour < 12:
            context += "现在是上午。"
        else:
            context += "现在是下午。"
        
        return context