#静态服务器返回
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple
from email.utils import format_datetime
from urllib.parse import unquote, urlsplit

import cchardet

from src.httpResolver.httpResolver import HttpVersion, HttpRequestData, ErrorReason, Method


def detect_encoding_fast(file_path: Path, common_encodings: list = None):
    """
    高性能探测文件编码，失败时返回安全的默认编码。
    """
    if common_encodings is None:
        # 按频率从高到低排列
        common_encodings = ['utf-8', 'gbk', 'shift_jis', 'latin-1']

    # 1. 尝试BOM头检测 (开销极小，优先执行)
    data_start = file_path.read_bytes()[:4]
    if data_start.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig'
    if data_start.startswith(b'\xff\xfe'):
        return 'utf-16-le'
    if data_start.startswith(b'\xfe\xff'):
        return 'utf-16-be'

    # 2. 回退策略: 尝试常用编码直接解码 (快速且准确)
    raw_data = file_path.read_bytes()
    for enc in common_encodings:
        try:
            raw_data.decode(enc)
            return enc  # 解码成功，直接返回
        except UnicodeDecodeError:
            continue  # 解码失败，尝试下一个

    # 3. 使用cchardet进行智能探测 (最终保障)
    try:
        result = cchardet.detect(raw_data)
        encoding = result['encoding']
        confidence = result['confidence']
        # 对于低置信度的结果，可选择记录日志或返回安全默认值
        if confidence > 0.85:
            return encoding
    except Exception:
        pass

    # 4. 最后的最后: 返回安全的默认值
    return 'utf-8'
class ResponseErrorReason(Enum):
    FILE_NOT_FOUND = 0
    BAD_PATH = 1
    METHOD_NOT_ALLOWED = 2

class FileResponser:
    def __init__(self,root:str,mime_types:dict[str,list[str]],default_mime:str="application/octet-stream"):
        self.root:str = root
        self.mime_types:dict[str,list[str]] = mime_types
        self.rev_mime_types:dict[str,str] = {}
        self.default_mime:str = default_mime
        for k,v in mime_types.items():
            for m in v:
                self.rev_mime_types[m]=k
    @staticmethod
    def secure_path(root_dir: str, user_path: str) -> Optional[str]|bool:
        """
        返回在 root_dir 内的绝对路径（必须存在），否则返回 None。

        规则：
        - root_dir 和拼接后的路径都必须真实存在（跟随符号链接）。
        - 如果 user_path 指向符号链接，会解析到最终目标，且目标必须在 root_dir 内。
        - 如果 user_path 是绝对路径，自动忽略 root_dir 并导致检查失败（除非巧合等于 root_dir）。
        - 返回的路径是经过 resolve 的绝对路径字符串。
        """
        try:
            # 根目录必须存在且解析为绝对路径
            root = Path(root_dir).resolve(strict=True)
        except FileNotFoundError:
            return None

        try:
            connected = Path(root , user_path)
            # 拼接并强制要求存在（strict=True 会跟随符号链接）
            #先检测是否是根外
            target0 = connected.resolve(strict=False)
            if not target0.is_relative_to(root):
                return False
            target = connected.resolve(strict=True)
        except FileNotFoundError:
            return None

        # 检查 target 是否在 root 之下（包括相等情况）
        return str(target)
        #return False
    @staticmethod
    def get_file_info_utc(path: Path) -> dict:
        """
        获取文件的修改时间（UTC+0）和大小（字节）。

        Args:
            path: 文件路径（Path 对象）

        Returns:
            包含文件信息的字典：
            {
                'size_bytes': int,
                'modified_utc': datetime.datetime (时区设为 UTC)
            }

        Raises:
            FileNotFoundError: 文件不存在
            OSError: 其他操作系统错误
        """
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在或不是普通文件: {path.absolute()}")

        stat = path.stat()
        size = stat.st_size
        # st_mtime 返回的是 Unix 时间戳（自 epoch 以来的秒数），本身基于 UTC
        modified_timestamp = stat.st_mtime
        modified_utc = datetime.fromtimestamp(modified_timestamp, tz=timezone.utc)

        return {
            'size_bytes': size,
            'modified_utc': modified_utc
        }
    #返回size,修改日期,tag,mime,encoding,path
    def fetch_content(self,relative_url:str) -> Optional[Tuple[int,datetime,str,str,str,Path]]|bool:
        secured = FileResponser.secure_path(self.root, relative_url)
        if secured is False:
            return False
        if secured is None:
            return None
        path=Path(secured)
        if not path.is_file():
            return None
        try:
            stats = FileResponser.get_file_info_utc(path)
            etag = format(stats['size_bytes'], 'x') + '-' + format(int(stats['modified_utc'].timestamp()), 'x')
            detect_mime = self.rev_mime_types.get(path.suffix) or self.rev_mime_types.get(path.suffix[1:]) or self.default_mime
            detect_encoding = detect_encoding_fast(path)
            return stats['size_bytes'],stats['modified_utc'],etag,detect_mime,detect_encoding,path
        except Exception as e:
            print(e)
            return None

class HttpResponse:
    def __init__(self,file_responser:FileResponser):
        self.http_version: HttpVersion = HttpVersion.Error
        self.status:int = 400
        self.reason: str = 'BadRequest'
        self.headers:dict[str, str] = {}
        self.body: bytes = b''
        self.file_responser: FileResponser = file_responser
        pass
    def reject(self,error: ErrorReason|ResponseErrorReason):
        self.status = 400
        self.reason = 'BadRequest'
        self.body = b''
        self.headers['Content-Length'] = '0'
        if error == ResponseErrorReason.FILE_NOT_FOUND:
            self.status = 404
            self.reason = 'Not Found'
        elif error == ResponseErrorReason.BAD_PATH:
            self.status = 403
            self.reason = 'Forbidden'
        elif error == ResponseErrorReason.METHOD_NOT_ALLOWED:
            self.status = 400
            self.reason = 'BadRequest'
            #错误请求的时候必须关闭链接
            self.headers['Connection'] = 'close'
        elif isinstance(error, ErrorReason):
            self.status = 400
            self.reason = 'BadRequest'
            #错误请求头的时候必须关闭链接
            self.headers['Connection'] = 'close'
        #错误的时候也有返回，不然会一直等着接受
        self.headers['Content-Length'] = '0'

    @staticmethod
    def _etag_match(if_none_match: list[str], etag: str) -> bool:
        if not if_none_match:
            return False
        current = etag.strip().strip('"')
        for raw in if_none_match:
            token = raw.strip()
            if token == '*':
                return True
            if token.startswith('W/'):
                token = token[2:].strip()
            token = token.strip('"')
            if token == current:
                return True
        return False

    @staticmethod
    def _is_not_modified(data: HttpRequestData, etag: str, modified_utc: datetime) -> bool:
        parsed = data.parsed_headers
        if parsed is None:
            return False
        if HttpResponse._etag_match(parsed.if_none_match, etag):
            return True
        if parsed.if_modified_since is not None and abs((modified_utc - parsed.if_modified_since).total_seconds()) < 1.0:
            return True
        return False

    @staticmethod
    def _normalize_url_to_path(url: str) -> str:
        raw_path = urlsplit(url).path
        normalized_slashes = unquote(raw_path).replace('\\', '/')
        parts: list[str] = []
        for seg in normalized_slashes.split('/'):
            if seg in ('', '.'):
                continue
            if seg == '..':
                if parts:
                    parts.pop()
                    continue
            parts.append(seg)
        return '/'.join(parts) or 'index.html'
    def resolve(self,data:HttpRequestData):
        self.http_version = data.http_version
        self.status = 200
        self.reason = 'OK'
        self.headers = {}
        self.body = b''
        self.headers['Date'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
        self.headers['Server'] = 'my-python-server'

        connection = 'keep-alive'
        if data.parsed_headers and data.parsed_headers.connection_tokens:
            values = [token.value for token in data.parsed_headers.connection_tokens]
            if 'close' in values:
                connection = 'close'
        self.headers['Connection'] = connection
        responder = self.file_responser
        if responder is None:
            self.reject(ResponseErrorReason.FILE_NOT_FOUND)
            return

        if data.method not in (Method.GET, Method.HEAD):
            self.reject(ResponseErrorReason.METHOD_NOT_ALLOWED)
            return
        meta = responder.fetch_content(self._normalize_url_to_path(data.url))
        if meta is False:
            self.reject(ResponseErrorReason.BAD_PATH)
            return
        elif meta is None:
            self.reject(ResponseErrorReason.FILE_NOT_FOUND)
            return

        size, modified_utc, etag, mime, encoding, path = meta
        self.headers['Content-Length'] = str(size)
        self.headers['Content-Type'] = f'{mime}; charset={encoding}'
        self.headers['ETag'] = etag
        self.headers['Last-Modified'] = format_datetime(modified_utc, usegmt=True)

        if HttpResponse._is_not_modified(data, etag, modified_utc):
            self.status = 304
            self.reason = 'NotModified'
            self.body = b''
            self.headers['Content-Length'] = '0'
            return

        if data.method == Method.GET:
            self.body = path.read_bytes()
        else:
            self.body = b''

    def _http_version_text(self) -> str:
        return self.http_version.value

    def serialize_status_line(self) -> bytes:
        line = f'{self._http_version_text()} {self.status} {self.reason}\r\n'
        return line.encode('ascii', errors='strict')

    def serialize_headers(self) -> bytes:
        rows: list[bytes] = []
        for key, value in self.headers.items():
            # Header name must be ASCII; value can use Latin-1 per HTTP/1.x compatibility.
            name_bytes = str(key).encode('ascii', errors='strict')
            value_bytes = str(value).encode('latin-1', errors='strict')
            rows.append(name_bytes + b': ' + value_bytes + b'\r\n')
        rows.append(b'\r\n')
        return b''.join(rows)

    def to_http_bytes(self) -> bytes:
        chunks = [self.serialize_status_line(), self.serialize_headers(),self.body]
        return b''.join(chunks)



