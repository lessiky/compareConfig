from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.models import ScheduledTask, ConfigMap, BusinessSystem, Server, current_time_plus_8
from app import db, scheduler
from datetime import datetime

bp = Blueprint('schedule', __name__)

def run_scheduled_task(task_id):
    """定时任务执行逻辑"""
    with scheduler.app.app_context():
        task = ScheduledTask.query.get(task_id)
        if not task or not task.is_active:
            return

        current_app.logger.info(f"Running Scheduled Task: {task.name} (ID: {task.id})")
        from app.services.diff_service import DiffService
        
        diff_service = DiffService()
        for config_map in task.config_maps:
            try:
                # 复用 DiffService 的比对逻辑
                # 注意：这里我们只执行比对并保存结果，不直接返回给前端
                # DiffService.compare_config_map 会将结果存入 DiffResult 表
                diff_service.compare_config_map(config_map)
            except Exception as e:
                current_app.logger.error(f"Error comparing config {config_map.id} in task {task.id}: {e}")
        
        task.last_run_at = current_time_plus_8()
        db.session.commit()

@bp.before_request
@login_required
def require_login():
    pass

@bp.route('/schedules')
def list_schedules():
    # 用户只能看到自己创建的任务，管理员可以看到所有
    if current_user.is_admin:
        tasks = ScheduledTask.query.all()
    else:
        tasks = ScheduledTask.query.filter_by(user_id=current_user.id).all()
    return render_template('schedule/list.html', tasks=tasks)

@bp.route('/schedules/add', methods=['GET', 'POST'])
def add_schedule():
    if request.method == 'POST':
        name = request.form.get('name')
        run_time = request.form.get('run_time') # HH:MM
        config_map_ids = request.form.getlist('config_map_ids')
        
        if not name or not run_time:
            flash('名称和时间为必填项', 'danger')
            return redirect(url_for('schedule.add_schedule'))
            
        task = ScheduledTask(
            name=name,
            run_time=run_time,
            user_id=current_user.id
        )
        
        # 处理选中的配置项
        for cm_id in config_map_ids:
            cm = ConfigMap.query.get(int(cm_id))
            if cm:
                task.config_maps.append(cm)
        
        db.session.add(task)
        db.session.commit()
        
        # 添加任务到 APScheduler
        hour, minute = run_time.split(':')
        scheduler.add_job(
            id=str(task.id),
            func=run_scheduled_task,
            args=[task.id],
            trigger='cron',
            hour=hour,
            minute=minute,
            misfire_grace_time=60  # 忽略错过的任务（例如宕机期间），只允许延迟60秒内的任务补执行
        )

        flash('定时任务创建成功', 'success')
        return redirect(url_for('schedule.list_schedules'))
    
    # GET 请求：准备配置项数据供选择
    if current_user.is_admin:
        servers = Server.query.all()
    else:
        system_ids = [sys.id for sys in current_user.authorized_systems]
        servers = Server.query.filter(Server.business_system_id.in_(system_ids)).all()
        
    return render_template('schedule/form.html', servers=servers)

@bp.route('/schedules/edit/<int:id>', methods=['GET', 'POST'])
def edit_schedule(id):
    task = ScheduledTask.query.get_or_404(id)
    
    # 权限检查
    if not current_user.is_admin and task.user_id != current_user.id:
        flash('无权编辑此任务', 'danger')
        return redirect(url_for('schedule.list_schedules'))
        
    if request.method == 'POST':
        task.name = request.form.get('name')
        new_run_time = request.form.get('run_time')
        config_map_ids = request.form.getlist('config_map_ids')
        
        # 更新配置项
        task.config_maps.clear()
        for cm_id in config_map_ids:
            cm = ConfigMap.query.get(int(cm_id))
            if cm:
                task.config_maps.append(cm)
        
        # 如果时间变了，需要更新调度器
        if task.run_time != new_run_time:
            task.run_time = new_run_time
            hour, minute = new_run_time.split(':')
            try:
                # 重新调度任务
                # 注意：Flask-APScheduler 没有直接暴露 reschedule_job，但可以通过 scheduler.scheduler 访问底层的 APScheduler 实例
                # 或者更简单地，先删除再添加
                try:
                    scheduler.remove_job(str(task.id))
                except:
                    pass
                    
                scheduler.add_job(
                    id=str(task.id),
                    func=run_scheduled_task,
                    args=[task.id],
                    trigger='cron',
                    hour=hour,
                    minute=minute,
                    misfire_grace_time=60  # 忽略错过的任务（例如宕机期间），只允许延迟60秒内的任务补执行
                )
            except Exception as e:
                current_app.logger.error(f"Error rescheduling job {task.id}: {e}")

        db.session.commit()
        flash('任务更新成功', 'success')
        return redirect(url_for('schedule.list_schedules'))

    # GET 请求
    if current_user.is_admin:
        servers = Server.query.all()
    else:
        system_ids = [sys.id for sys in current_user.authorized_systems]
        servers = Server.query.filter(Server.business_system_id.in_(system_ids)).all()
        
    return render_template('schedule/form.html', task=task, servers=servers)

@bp.route('/schedules/delete/<int:id>', methods=['POST'])
def delete_schedule(id):
    task = ScheduledTask.query.get_or_404(id)
    
    if not current_user.is_admin and task.user_id != current_user.id:
        flash('无权删除此任务', 'danger')
        return redirect(url_for('schedule.list_schedules'))
        
    try:
        scheduler.remove_job(str(task.id))
    except:
        pass # 任务可能不在调度器中
        
    db.session.delete(task)
    db.session.commit()
    flash('任务已删除', 'success')
    return redirect(url_for('schedule.list_schedules'))

@bp.route('/schedules/toggle/<int:id>', methods=['POST'])
def toggle_schedule(id):
    """启用/停用任务"""
    task = ScheduledTask.query.get_or_404(id)
    
    if not current_user.is_admin and task.user_id != current_user.id:
        flash('无权操作此任务', 'danger')
        return redirect(url_for('schedule.list_schedules'))
        
    task.is_active = not task.is_active
    
    if task.is_active:
        try:
            scheduler.resume_job(str(task.id))
        except:
             # 如果任务不存在（比如重启后），则重新添加
            hour, minute = task.run_time.split(':')
            scheduler.add_job(
                id=str(task.id),
                func=run_scheduled_task,
                args=[task.id],
                trigger='cron',
                hour=hour,
                minute=minute,
                misfire_grace_time=60  # 忽略错过的任务（例如宕机期间），只允许延迟60秒内的任务补执行
            )
    else:
        try:
            scheduler.pause_job(str(task.id))
        except:
            pass
            
    db.session.commit()
    return redirect(url_for('schedule.list_schedules'))
