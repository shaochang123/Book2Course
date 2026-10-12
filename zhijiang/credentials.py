"""Windows-user-encrypted credentials, scoped to a service and exact endpoint."""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from urllib.parse import urlsplit,urlunsplit


class CredentialError(RuntimeError):pass


def endpoint(value: str) -> str:
    p=urlsplit(value.strip())
    if (p.scheme not in {'http','https'} or not p.hostname or p.username or p.password
            or p.query or p.fragment):
        raise ValueError('请输入不包含账号、密钥参数的 HTTP(S) API 地址。')
    try:port=p.port
    except ValueError as exc:raise ValueError('API 地址端口无效。') from exc
    host=p.hostname.lower()
    if ':' in host:host='['+host+']'
    if port and port!=({'http':80,'https':443}[p.scheme]):host+=':'+str(port)
    return urlunsplit((p.scheme,host,p.path.rstrip('/'),'',''))


def _transform(data: bytes, *, decrypt=False) -> bytes:
    if sys.platform!='win32':raise CredentialError('当前平台请通过本机环境配置保存密钥。')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));result=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    function=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.POINTER(Blob),
                       ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    function.restype=wintypes.BOOL
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(result)):
        raise CredentialError('本机账户的密钥加密存储无法读取或写入。')
    free=ctypes.WinDLL('kernel32').LocalFree
    free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
    try:return ctypes.string_at(result.data,result.size)
    finally:
        if decrypt:ctypes.memset(result.data,0,result.size)
        free(ctypes.cast(result.data,ctypes.c_void_p))
        ctypes.memset(buffer,0,len(data))


class LocalCredentials:
    def __init__(self,data_dir: Path):
        self.path=data_dir/'private'/'credentials.dpapi'
        self.lock=threading.RLock()
        self.supported=sys.platform=='win32'

    @staticmethod
    def _id(kind,provider,base_url):
        if kind not in {'llm','tts'} or provider not in {'openai','ollama'}:raise ValueError('未知密钥类型。')
        return hashlib.sha256(json.dumps([kind,provider,endpoint(base_url)]).encode()).hexdigest()

    def _load(self):
        if not self.path.is_file():return {}
        try:
            data=json.loads(_transform(self.path.read_bytes(),decrypt=True))
            if not isinstance(data,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in data.items()):
                raise ValueError('Invalid credential structure')
            return data
        except (OSError,ValueError) as exc:raise CredentialError('保存的密钥无法读取，请重新配置。') from exc

    def _write(self,data):
        pending=self.path.with_suffix('.pending')
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            pending.write_bytes(_transform(json.dumps(data,ensure_ascii=False).encode()))
            os.replace(pending,self.path)
        except OSError as exc:raise CredentialError('密钥保存失败，请检查本地数据目录的写入权限。') from exc
        finally:
            try:pending.unlink(missing_ok=True)
            except OSError:pass  # A cleanup error must not expose paths or replace the safe error.

    def get(self,kind,provider,base_url):
        if not self.supported:return None
        key=self._id(kind,provider,base_url)
        with self.lock:return self._load().get(key)

    def save(self,kind,provider,base_url,api_key):
        if not self.supported:raise CredentialError('当前平台请通过本机环境配置保存密钥。')
        key=self._id(kind,provider,base_url)
        with self.lock:
            data=self._load();data[key]=api_key.strip();self._write(data)

    def remove(self,kind,provider,base_url):
        key=self._id(kind,provider,base_url)
        with self.lock:
            data=self._load();data.pop(key,None)
            if self.path.exists():self._write(data)
