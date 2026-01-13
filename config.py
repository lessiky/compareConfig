import os
import configparser

# 读取配置文件
config = configparser.ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), 'config.ini'))

class Config:
    # 数据库配置
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        config.get('database', 'url', fallback='mysql+pymysql://user:password@localhost/compare_config_db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # GitLab 配置
    GITLAB_URL = os.environ.get('GITLAB_URL') or config.get('gitlab', 'url')
    GITLAB_TOKEN = os.environ.get('GITLAB_TOKEN') or config.get('gitlab', 'token')
    GITLAB_PROJECT_ID = os.environ.get('GITLAB_PROJECT_ID') or config.get('gitlab', 'project_id')
    
    # SSH 默认配置
    SSH_KEY_PATH = os.environ.get('SSH_KEY_PATH') or config.get('ssh', 'key_path', fallback='id_rsa')
    
    SECRET_KEY = os.environ.get('SECRET_KEY') or config.get('flask', 'secret_key')
