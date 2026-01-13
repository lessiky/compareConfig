import os
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_apscheduler import APScheduler
from config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录'
scheduler = APScheduler()

def configure_logging(app):
    """配置日志"""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'log')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 移除默认的处理器
    app.logger.handlers.clear()
    
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    
    log_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, 'compareConfig.log'), 
        when='midnight', 
        interval=1, 
        backupCount=30,
        encoding='utf-8'
    )
    log_handler.suffix = "_%Y%m%d"
    # 需要配合 namer 才能完全控制文件名，但 Python logging 默认行为是 filename + suffix
    # 所以 filename='compareConfig' + suffix='_20230101.log' => compareConfig_20230101.log
    # 这是一个非常接近的方案。
    
    log_handler.setFormatter(formatter)
    log_handler.setLevel(logging.INFO)
    
    app.logger.addHandler(log_handler)
    app.logger.setLevel(logging.INFO)
    
    # 同时输出到控制台，方便调试
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    app.logger.addHandler(console_handler)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    configure_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    
    # 初始化调度器
    scheduler.init_app(app)
    
    # 恢复任务：从数据库读取并重新添加到调度器
    # 注意：这里需要放在应用上下文之后，且避免在 db migrate 等命令时执行
    with app.app_context():
        # 避免在非运行状态（如迁移）下查询数据库导致表不存在报错
        try:
            from app.models import ScheduledTask
            from app.schedule_routes import run_scheduled_task
            
            # 只有当表存在时才执行
            inspector = db.inspect(db.engine)
            if 'scheduled_tasks' in inspector.get_table_names():
                tasks = ScheduledTask.query.filter_by(is_active=True).all()
                for task in tasks:
                    try:
                        hour, minute = task.run_time.split(':')
                        # 检查任务是否已存在（避免热重载重复添加）
                        if not scheduler.get_job(str(task.id)):
                            scheduler.add_job(
                                id=str(task.id),
                                func=run_scheduled_task,
                                args=[task.id],
                                trigger='cron',
                                hour=hour,
                                minute=minute,
                                replace_existing=True,
                                misfire_grace_time=60  # 忽略错过的任务（例如宕机期间），只允许延迟60秒内的任务补执行
                            )
                    except Exception as e:
                        app.logger.error(f"Failed to restore task {task.id}: {e}")
        except Exception as e:
            app.logger.warning(f"Skipping task restoration: {e}")
            
    scheduler.start()

    # 注册蓝图/路由
    from app import routes, models
    app.register_blueprint(routes.bp)
    
    from app.auth.routes import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.system_routes import bp as system_bp
    app.register_blueprint(system_bp)
    
    from app.server_routes import bp as server_bp
    app.register_blueprint(server_bp)
    
    from app.user_routes import bp as user_bp
    app.register_blueprint(user_bp)
    
    from app.schedule_routes import bp as schedule_bp
    app.register_blueprint(schedule_bp)
    
    from app.dirpair_routes import bp as dirpair_bp
    app.register_blueprint(dirpair_bp)
    
    # 用户加载回调
    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    return app
