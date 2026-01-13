import openpyxl
from app import db
from app.models import Server
from cryptography.fernet import Fernet
import os
import base64
from flask import current_app

# 获取或生成密钥
# 在生产环境中，这个密钥应该安全存储（如环境变量），而不是硬编码或每次生成
# 这里为了演示方便，如果环境变量没有，我们尝试读取本地文件，否则生成一个（注意：每次重启生成会导致之前的数据无法解密）
KEY_FILE = 'secret.key'

def get_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, 'wb') as f:
            f.write(key)
        return key

CIPHER_SUITE = Fernet(get_key())

def encrypt_password(password):
    if not password:
        return None
    if isinstance(password, str):
        password = password.encode('utf-8')
    return CIPHER_SUITE.encrypt(password).decode('utf-8')

def decrypt_password(encrypted_password):
    if not encrypted_password:
        return None
    if isinstance(encrypted_password, str):
        encrypted_password = encrypted_password.encode('utf-8')
    try:
        return CIPHER_SUITE.decrypt(encrypted_password).decode('utf-8')
    except Exception:
        # 解密失败可能是因为密钥变了或者数据不是加密格式
        return encrypted_password.decode('utf-8') if isinstance(encrypted_password, bytes) else encrypted_password

def import_servers_from_excel(file_path):
    try:
        wb = openpyxl.load_workbook(file_path)
        sheet = wb.active
        
        # Skip header row
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
                
            ip = row[0]
            username = row[1]
            password = row[2]
            
            # Encrypt password
            encrypted_pwd = encrypt_password(password)
            
            # Simple check if server exists
            server = Server.query.filter_by(ip=ip).first()
            if server:
                server.username = username
                server.password = encrypted_pwd
            else:
                # Name default to IP if not provided
                server = Server(name=ip, ip=ip, username=username, password=encrypted_pwd)
                db.session.add(server)
        
        db.session.commit()
        if current_app:
            current_app.logger.info(f"Successfully imported servers from {file_path}")
    except Exception as e:
        if current_app:
            current_app.logger.error(f"Error importing servers from Excel: {e}")
        else:
            print(f"Error importing servers from Excel: {e}")
