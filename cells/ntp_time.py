import socket
import struct
import time
import datetime
import logging
from typing import Optional, Tuple

class NTPClient:
    """NTP客户端，用于从NTP服务器获取准确时间"""
    
    def __init__(self, server="ntp.aliyun.com", port=123, timeout=5):
        """
        初始化NTP客户端
        
        Args:
            server: NTP服务器地址，默认为阿里云NTP服务器
            port: NTP服务端口，默认为123
            timeout: 超时时间（秒）
        """
        self.server = server
        self.port = port
        self.timeout = timeout
        self.logger = logging.getLogger("NTPClient")
    
    def get_ntp_time(self) -> Optional[datetime.datetime]:
        """
        从NTP服务器获取当前时间
        
        Returns:
            datetime对象，如果获取失败则返回None
        """
        try:
            # NTP请求包格式
            # 详见RFC 5905: https://datatracker.ietf.org/doc/html/rfc5905
            ntp_request = b'\x1b' + 47 * b'\0'
            
            # 创建UDP socket
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(self.timeout)
                
                # 发送请求到NTP服务器
                sock.sendto(ntp_request, (self.server, self.port))
                
                # 接收响应
                data, _ = sock.recvfrom(1024)
                
                if data:
                    # 解析NTP响应
                    # 时间戳位于响应的第40-43字节（秒）和44-47字节（分数秒）
                    seconds = struct.unpack('!I', data[40:44])[0]
                    
                    # NTP时间从1900年开始，而Unix时间从1970年开始
                    # 两者相差70年（包括17个闰年）
                    ntp_timestamp = seconds - 2208988800
                    
                    # 转换为datetime对象
                    dt = datetime.datetime.fromtimestamp(ntp_timestamp)
                    return dt
            
        except Exception as e:
            self.logger.error(f"获取NTP时间失败: {str(e)}")
            return None
        
        return None
    
    def get_formatted_time(self, timezone_offset: int = 8) -> Optional[str]:
        """
        获取格式化的时间字符串
        
        Args:
            timezone_offset: 时区偏移量（小时），默认为东八区(+8)
            
        Returns:
            格式化的时间字符串，格式为"年月日时分"，如果获取失败则返回None
        """
        dt = self.get_ntp_time()
        if dt:
            # 应用时区偏移
            dt = dt + datetime.timedelta(hours=timezone_offset)
            
            # 格式化时间
            hour = dt.hour
            period = "上午"
            if hour >= 12:
                period = "下午"
            
            formatted_time = dt.strftime(f"%y年%m月%d日{period}%H时%M分")
            return formatted_time
        
        return None
    
    def get_time_tuple(self, timezone_offset: int = 8) -> Tuple[Optional[datetime.datetime], Optional[str]]:
        """
        获取时间元组，包含datetime对象和格式化的时间字符串
        
        Args:
            timezone_offset: 时区偏移量（小时），默认为东八区(+8)
            
        Returns:
            (datetime对象, 格式化的时间字符串)，如果获取失败则相应位置为None
        """
        dt = self.get_ntp_time()
        formatted_time = None
        
        if dt:
            # 应用时区偏移
            dt_with_tz = dt + datetime.timedelta(hours=timezone_offset)
            
            # 格式化时间
            hour = dt_with_tz.hour
            period = "上午"
            if hour >= 12:
                period = "下午"
            
            formatted_time = dt_with_tz.strftime(f"%y年%m月%d日{period}%H时%M分")
            
        return (dt, formatted_time)