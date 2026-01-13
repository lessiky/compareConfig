from app import db
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

# 关联表：用户与业务系统
user_business_system = db.Table('user_business_system',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('business_system_id', db.Integer, db.ForeignKey('business_systems.id'), primary_key=True)
)

def current_time_plus_8():
    return datetime.utcnow() + timedelta(hours=8)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # 授权的业务系统
    authorized_systems = db.relationship('BusinessSystem', secondary=user_business_system, lazy='subquery',
        backref=db.backref('users', lazy=True))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class BusinessSystem(db.Model):
    __tablename__ = 'business_systems'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True, unique=True, nullable=False)
    description = db.Column(db.String(256))
    
    servers = db.relationship('Server', backref='business_system', lazy='dynamic')

    def __repr__(self):
        return f'<BusinessSystem {self.name}>'

class Server(db.Model):
    __tablename__ = 'servers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True, unique=True)
    ip = db.Column(db.String(64), nullable=False)
    port = db.Column(db.Integer, default=22)
    username = db.Column(db.String(64), nullable=False)
    password = db.Column(db.String(128), nullable=True) # 从 Excel 读取
    os_type = db.Column(db.String(20), default='Linux') # Windows or Linux
    ssh_key_path = db.Column(db.String(256), nullable=True) # 如果为空，使用全局默认
    
    business_system_id = db.Column(db.Integer, db.ForeignKey('business_systems.id'), nullable=True)
    
    config_maps = db.relationship('ConfigMap', backref='server', lazy='dynamic')

    def __repr__(self):
        return f'<Server {self.name} ({self.ip})>'

class ConfigMap(db.Model):
    __tablename__ = 'config_maps'
    
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id'), nullable=False)
    remote_path = db.Column(db.String(256), nullable=False) # 服务器上的目录或文件路径
    gitlab_path = db.Column(db.String(256), nullable=False) # GitLab 仓库中的路径
    file_pattern = db.Column(db.String(256), default='*') # 例如 *.conf
    
    diff_results = db.relationship('DiffResult', backref='config_map', lazy='dynamic')

    def __repr__(self):
        return f'<ConfigMap {self.remote_path} -> {self.gitlab_path}>'

class DiffResult(db.Model):
    __tablename__ = 'diff_results'
    
    id = db.Column(db.Integer, primary_key=True)
    config_map_id = db.Column(db.Integer, db.ForeignKey('config_maps.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=current_time_plus_8)
    file_name = db.Column(db.String(128), nullable=False)
    status = db.Column(db.String(20), nullable=False) # MATCH, DIFF, MISSING_LOCAL, MISSING_REMOTE
    diff_content = db.Column(db.Text, nullable=True) # 具体的 diff 文本

    def __repr__(self):
        return f'<DiffResult {self.file_name} - {self.status}>'

# 关联表：定时任务与配置项
task_config_maps = db.Table('task_config_maps',
    db.Column('task_id', db.Integer, db.ForeignKey('scheduled_tasks.id'), primary_key=True),
    db.Column('config_map_id', db.Integer, db.ForeignKey('config_maps.id'), primary_key=True)
)

class ScheduledTask(db.Model):
    __tablename__ = 'scheduled_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    # 使用 cron 风格的时间设置，这里为了简化，我们只存储 hour 和 minute
    # 如果需要更复杂，可以存储 cron 表达式
    run_time = db.Column(db.String(10), nullable=False) # 格式 "HH:MM"
    is_active = db.Column(db.Boolean, default=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=current_time_plus_8)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', backref='scheduled_tasks')
    
    config_maps = db.relationship('ConfigMap', secondary=task_config_maps, lazy='subquery',
        backref=db.backref('scheduled_tasks', lazy=True))

    def __repr__(self):
        return f'<ScheduledTask {self.name} at {self.run_time}>'

class DirectoryPair(db.Model):
    __tablename__ = 'directory_pairs'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    left_server_id = db.Column(db.Integer, db.ForeignKey('servers.id'), nullable=False)
    left_path = db.Column(db.String(256), nullable=False)
    right_server_id = db.Column(db.Integer, db.ForeignKey('servers.id'), nullable=False)
    right_path = db.Column(db.String(256), nullable=False)
    file_pattern = db.Column(db.String(64), default='*')
    created_at = db.Column(db.DateTime, default=current_time_plus_8)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    left_server = db.relationship('Server', foreign_keys=[left_server_id])
    right_server = db.relationship('Server', foreign_keys=[right_server_id])
    user = db.relationship('User', backref='directory_pairs')
    results = db.relationship('DirectoryDiffResult', backref='pair', lazy='dynamic')
    
    def __repr__(self):
        return f'<DirectoryPair {self.name}>'

from sqlalchemy.dialects.mysql import LONGTEXT

class DirectoryDiffResult(db.Model):
    __tablename__ = 'directory_diff_results'
    
    id = db.Column(db.Integer, primary_key=True)
    pair_id = db.Column(db.Integer, db.ForeignKey('directory_pairs.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=current_time_plus_8)
    file_name = db.Column(db.String(256), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    diff_content = db.Column(LONGTEXT, nullable=True)
    left_content = db.Column(LONGTEXT, nullable=True) # 保存左侧文件原始内容
    right_content = db.Column(LONGTEXT, nullable=True) # 保存右侧文件原始内容
    
    def __repr__(self):
        return f'<DirectoryDiffResult {self.file_name} - {self.status}>'
