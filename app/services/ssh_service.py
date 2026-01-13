import paramiko
import os
from flask import current_app
from app.utils import decrypt_password

class SSHService:
    def __init__(self, host, username, password=None, key_path=None, port=22, os_type='Linux'):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.key_path = key_path
        self.os_type = os_type
        self.client = None

    def _get_key_path(self):
        if self.key_path:
            return self.key_path
        return current_app.config.get('SSH_KEY_PATH')

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            if self.password:
                # Decrypt password before connecting
                plain_password = decrypt_password(self.password)
                self.client.connect(hostname=self.host, port=self.port, username=self.username, password=plain_password)
                return

            key_file = self._get_key_path()
            if key_file and os.path.exists(key_file):
                # 尝试多种密钥格式
                try:
                    k = paramiko.RSAKey.from_private_key_file(key_file)
                except:
                    try:
                        k = paramiko.Ed25519Key.from_private_key_file(key_file)
                    except:
                        # 如果都不是，可能需要其他处理，这里暂且只支持这两种常见格式，或者不指定 pkey 让 paramiko 自己尝试
                        # paramiko.SSHClient.connect 的 key_filename 参数其实更智能
                        k = None
                
                if k:
                    self.client.connect(hostname=self.host, port=self.port, username=self.username, pkey=k)
                else:
                     self.client.connect(hostname=self.host, port=self.port, username=self.username, key_filename=key_file)
            else:
                # 尝试默认连接（如使用系统 SSH 配置）
                self.client.connect(hostname=self.host, port=self.port, username=self.username)
        except Exception as e:
            current_app.logger.error(f"Failed to connect to {self.host}: {e}")
            raise

    def list_files(self, remote_path, pattern='*'):
        if not self.client:
            self.connect()
        
        # 规范化路径，移除末尾的 /
        remote_path = remote_path.rstrip('/\\')
        
        # 处理多个 pattern，用 ; 分隔
        patterns = [p.strip() for p in pattern.split(';') if p.strip()]
        if not patterns:
            patterns = ['*']
            
        if self.os_type == 'Windows':
            # Windows 处理逻辑
            # dir /s /b "path\pattern1" "path\pattern2" | findstr /v /a:d "^$"
            # dir 的 /a-d 参数其实是过滤掉目录，但 dir "path\pattern" 时 /a-d 并不总是生效，尤其是配合 /s 时行为可能不一致
            # 但最重要的是，Windows cmd 的参数解析问题。
            
            # Windows 路径通常使用反斜杠
            remote_path_win = remote_path.replace('/', '\\')
            
            # 使用简单的 dir 命令，多次执行然后合并结果
            # dir /s /b /a-d "root\pattern"
            
            files = []
            for p in patterns:
                # 拼接路径和通配符
                # 注意：Windows 命令行中，如果路径包含双重引号会导致解析错误
                # 比如 "D:\path\"pattern"" 是非法的
                # 我们应该只在整个路径外层加一次引号，且只有当路径包含空格时才必须加，但通常加了比较安全
                # 这里的 full_pattern 已经是拼接好的路径，例如 D:\path\pattern
                
                # 如果 remote_path_win 已经带了引号，先去掉
                remote_path_clean = remote_path_win.strip('"')
                p_clean = p.strip('"')
                
                full_pattern = f'{remote_path_clean}\\{p_clean}'
                # 统一将双反斜杠替换为单反斜杠（Windows API 和 cmd 有时对连续的 \\ 处理不一致）
                # 虽然 Python 字符串中 \\ 表示一个反斜杠，但这里我们希望最终传给 cmd 的是一个干净的路径
                # 比如 D:\path\\file.txt -> D:\path\file.txt
                full_pattern = full_pattern.replace('\\\\', '\\')
                
                # 注意：Windows dir 命令对 /a-d 的支持
                # cmd = f'dir /s /b /a-d "{full_pattern}"'
                
                # 改用 cmd /c 来执行，确保环境一致
                # cmd /c "dir /s /b /a-d "path""
                cmd = f'cmd /c "dir /s /b /a-d "{full_pattern}""'
                
                try:
                    stdin, stdout, stderr = self.client.exec_command(cmd)
                    
                    # Windows 命令行输出可能是 GBK 编码
                    try:
                        output = stdout.read().decode('gbk')
                    except:
                        output = stdout.read().decode('utf-8', errors='replace')
                        
                    # dir 找不到文件时会输出到 stderr，但这不算严重错误
                    # error = stderr.read().decode('gbk', errors='replace')
                    
                    for line in output.splitlines():
                        if line.strip():
                            files.append(line.strip())
                except Exception as e:
                    current_app.logger.error(f"Error executing dir command for {full_pattern}: {e}")

            # 去重
            files = list(set(files))
            return files
            
        else:
            # Linux 处理逻辑 (保持原有)
            # 构建 find 命令，使用 -o (OR) 连接多个 -name 条件
            # find path -maxdepth 1 \( -name 'p1' -o -name 'p2' \) -type f
            name_conditions = []
            for p in patterns:
                name_conditions.append(f"-name '{p}'")
            
            condition_str = " -o ".join(name_conditions)
            if len(patterns) > 1:
                condition_str = f"\\( {condition_str} \\)"
                
            cmd = f"find {remote_path} -maxdepth 1 {condition_str} -type f"
            stdin, stdout, stderr = self.client.exec_command(cmd)
            
            error = stderr.read().decode('utf-8')
            if error:
                current_app.logger.error(f"Error listing files: {error}")
                
            files = []
            for line in stdout:
                files.append(line.strip())
                
            return files

    def read_file(self, file_path):
        if not self.client:
            self.connect()
            
        sftp = self.client.open_sftp()
        try:
            with sftp.open(file_path, 'r') as f:
                # 尝试读取并解码，处理可能的编码问题
                content = f.read()
                for enc in ('utf-8', 'gb18030', 'gbk', 'utf-16-le', 'latin-1'):
                    try:
                        return content.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return content.decode('utf-8', errors='replace')
        except Exception as e:
            current_app.logger.error(f"Error reading file {file_path}: {e}")
            return None
        finally:
            sftp.close()

    def close(self):
        if self.client:
            self.client.close()
