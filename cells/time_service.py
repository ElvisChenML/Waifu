import ntplib
import time
import datetime
import pytz
import functools
import logging
from pkg.core import app


def handle_errors(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # self.ap.logger 是类的属性，这里使用 args[0] 代表实例对象
            args[0].ap.logger.error(f"时间服务错误：{e}")
            return None

    return wrapper


class TimeService:
    """
    时间服务类，用于获取NTP服务器时间并转换为指定时区的时间
    """

    ap: app.Application

    def __init__(self, ap: app.Application):
        """
        初始化时间服务
        :param ap: Application实例
        """
        self.ap = ap
        self.enabled = False
        self.timezone = "Asia/Shanghai"
        self.ntp_server = "ntp.aliyun.com"
        self.sync_interval = 3600  # 默认每小时同步一次
        self.last_sync_time = 0
        self.time_offset = 0  # 本地时间与NTP服务器时间的偏差
        self.ntp_client = ntplib.NTPClient()

    async def load_config(self, config_data):
        """
        从配置数据加载时间服务配置
        """
        # 直接从传入的配置数据中获取时间服务配置
        time_service_config = config_data.get("time_service", {})
        self.enabled = time_service_config.get("enabled", True)
        self.ntp_server = time_service_config.get("ntp_server", "ntp.aliyun.com")
        self.timezone = time_service_config.get("timezone", "Asia/Shanghai")
        self.include_date = time_service_config.get("include_date", True)
        self.include_time = time_service_config.get("include_time", True)
        self.include_timezone = time_service_config.get("include_timezone", False)
        self.sync_interval = time_service_config.get("sync_interval", 3600)
        
        # 初始化时间同步
        if self.enabled:
            await self.sync_time()

    @handle_errors
    async def sync_time(self):
        """
        与NTP服务器同步时间
        """
        if not self.enabled:
            return
            
        current_time = time.time()
        
        # 检查是否需要同步时间
        if current_time - self.last_sync_time < self.sync_interval:
            return
            
        try:
            # 获取NTP服务器时间
            response = self.ntp_client.request(self.ntp_server, version=3)
            # 计算本地时间与NTP服务器时间的偏差
            self.time_offset = response.offset
            self.last_sync_time = current_time
            self.ap.logger.info(f"与NTP服务器{self.ntp_server}同步时间成功，偏差：{self.time_offset:.6f}秒")
        except Exception as e:
            self.ap.logger.error(f"与NTP服务器{self.ntp_server}同步时间失败：{e}")

    @handle_errors
    async def get_current_time(self):
        """
        获取当前时间，如果启用了时间服务，则返回NTP校准后的时间
        :return: 当前时间的datetime对象
        """
        if not self.enabled:
            return None
            
        # 检查是否需要同步时间
        await self.sync_time()
        
        # 获取校准后的当前时间戳
        current_timestamp = time.time() + self.time_offset
        
        # 转换为datetime对象
        utc_time = datetime.datetime.fromtimestamp(current_timestamp, tz=pytz.UTC)
        
        # 转换为指定时区的时间
        try:
            local_timezone = pytz.timezone(self.timezone)
            local_time = utc_time.astimezone(local_timezone)
            return local_time
        except Exception as e:
            self.ap.logger.error(f"时区转换失败：{e}")
            return utc_time

    @handle_errors
    async def get_time_info(self):
        """
        获取格式化的时间信息，用于发送给大模型
        :return: 格式化的时间信息字符串
        """
        if not self.enabled:
            return ""
            
        current_time = await self.get_current_time()
        if not current_time:
            return ""
            
        # 格式化时间信息
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekday_names[current_time.weekday()]
        
        time_info = f"当前时间：{current_time.strftime('%Y年%m月%d日 %H:%M:%S')} {weekday}，时区：{self.timezone}"
        return time_info