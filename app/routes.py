from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from app import db
from app.models import Server, ConfigMap, DiffResult
from app.services.diff_service import DiffService
from flask_login import login_required, current_user

bp = Blueprint('main', __name__)

@bp.before_request
@login_required
def require_login():
    pass

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/configs')
def list_configs():
    if current_user.is_admin:
        servers = Server.query.all()
    else:
        system_ids = [sys.id for sys in current_user.authorized_systems]
        servers = Server.query.filter(Server.business_system_id.in_(system_ids)).all()
        
    return render_template('config/list.html', servers=servers)

@bp.route('/server/add', methods=['POST'])
def add_server():
    # 废弃的路由，功能已迁移到 server_routes
    pass

@bp.route('/config/add', methods=['POST'])
def add_config():
    server_id = request.form.get('server_id')
    
    # 权限检查
    server = Server.query.get_or_404(server_id)
    if not current_user.is_admin:
        if server.business_system_id not in [sys.id for sys in current_user.authorized_systems]:
            abort(403)
            
    remote_path = request.form.get('remote_path')
    gitlab_path = request.form.get('gitlab_path')
    file_pattern = request.form.get('file_pattern', '*')
    
    config = ConfigMap(server_id=server_id, remote_path=remote_path, gitlab_path=gitlab_path, file_pattern=file_pattern)
    db.session.add(config)
    db.session.commit()
    flash('Config map added successfully!', 'success')
    return redirect(url_for('main.list_configs'))

@bp.route('/compare/<int:config_id>')
def compare(config_id):
    config = ConfigMap.query.get_or_404(config_id)
    
    # 权限检查
    if not current_user.is_admin:
        if config.server.business_system_id not in [sys.id for sys in current_user.authorized_systems]:
            abort(403)
            
    service = DiffService()
    try:
        service.compare_config_map(config)
        flash('Comparison completed successfully!', 'success')
    except Exception as e:
        flash(f'Error during comparison: {str(e)}', 'danger')
        
    return redirect(url_for('main.view_results', config_id=config_id))

from app.services.ssh_service import SSHService
from app.services.gitlab_service import GitLabService
import posixpath
from flask_login import current_user

@bp.route('/sync', methods=['POST'])
def sync_to_gitlab():
    result_ids = request.form.getlist('result_ids')
    if not result_ids:
        flash('No files selected for sync.', 'warning')
        return redirect(request.referrer)
        
    gitlab_service = GitLabService()
    success_count = 0
    fail_count = 0
    
    for rid in result_ids:
        result = DiffResult.query.get(rid)
        if not result:
            continue
            
        config = result.config_map
        server = config.server
        
        # 权限检查
        if not current_user.is_admin:
            if server.business_system_id not in [sys.id for sys in current_user.authorized_systems]:
                # Skip unauthorized
                continue
        
        # 1. 读取服务器上的最新内容
        ssh = SSHService(server.ip, server.username, password=server.password, key_path=server.ssh_key_path, port=server.port, os_type=server.os_type)
        try:
            remote_full_path = posixpath.join(config.remote_path, result.file_name)
            content = ssh.read_file(remote_full_path)
            
            if content is None:
                flash(f'Failed to read {result.file_name} from server.', 'danger')
                fail_count += 1
                continue
                
            # 2. 提交到 GitLab
            # 假设 gitlab_path 是目录，我们需要拼接文件名
            # 但 DiffService 中我们建立了一个 map，这里简单起见，假设 gitlab_path 就是目录
            # 如果 gitlab_path 是 'configs/nginx'，filename 是 'site.conf'
            # 那么目标路径是 'configs/nginx/site.conf'
            target_gitlab_path = posixpath.join(config.gitlab_path, result.file_name)
            
            ok, msg = gitlab_service.update_file(
                file_path=target_gitlab_path,
                content=content,
                commit_message=f"Sync {result.file_name} from {server.name}"
            )
            
            if ok:
                success_count += 1
                # 更新 DiffResult 状态? 
                # 也许不需要，下次对比自然就 MATCH 了
            else:
                flash(f'Failed to sync {result.file_name}: {msg}', 'danger')
                fail_count += 1
                
        except Exception as e:
            flash(f'Error processing {result.file_name}: {str(e)}', 'danger')
            fail_count += 1
        finally:
            ssh.close()
            
    if success_count > 0:
        flash(f'Successfully synced {success_count} files.', 'success')
        
    return redirect(request.referrer)

@bp.route('/history/batch', methods=['POST'])
def batch_history():
    config_ids = request.form.getlist('config_ids')
    if not config_ids:
        flash('请至少选择一个配置项查看历史', 'warning')
        return redirect(url_for('main.list_configs'))
        
    ids_str = ','.join(config_ids)
    return redirect(url_for('main.view_batch_results', ids=ids_str))

@bp.route('/compare/batch', methods=['POST'])
def batch_compare():
    config_ids = request.form.getlist('config_ids')
    if not config_ids:
        flash('请至少选择一个配置项进行比对', 'warning')
        return redirect(url_for('main.list_configs'))
        
    service = DiffService()
    success_count = 0
    error_count = 0
    
    for cid in config_ids:
        config = ConfigMap.query.get(cid)
        if config:
            # 权限检查
            if not current_user.is_admin:
                if config.server.business_system_id not in [sys.id for sys in current_user.authorized_systems]:
                    continue
                    
            try:
                service.compare_config_map(config)
                success_count += 1
            except Exception as e:
                current_app.logger.error(f"Error comparing config {cid}: {e}")
                error_count += 1
    
    if success_count > 0:
        flash(f'成功比对 {success_count} 个配置项', 'success')
    if error_count > 0:
        flash(f'{error_count} 个配置项比对失败，请检查日志', 'danger')
        
    # 重定向到 GET 路由来展示结果，避免刷新或重定向回 POST 时的 Method Not Allowed 问题
    ids_str = ','.join(config_ids)
    return redirect(url_for('main.view_batch_results', ids=ids_str))

@bp.route('/results/batch')
def view_batch_results():
    ids_str = request.args.get('ids', '')
    if not ids_str:
        return redirect(url_for('main.list_configs'))
        
    config_ids = [int(x) for x in ids_str.split(',') if x.isdigit()]
    
    # 获取所有选中的 config 的结果，准备展示
    configs = ConfigMap.query.filter(ConfigMap.id.in_(config_ids)).all()
    
    # 过滤权限
    if not current_user.is_admin:
        configs = [c for c in configs if c.server.business_system_id in [sys.id for sys in current_user.authorized_systems]]
        
    grouped_results = []
    for c in configs:
        res = c.diff_results.order_by(DiffResult.created_at.desc()).all()
        if res:
            grouped_results.append((c, res))
            
    return render_template('results.html', grouped_results=grouped_results)

@bp.route('/results/<int:config_id>')
def view_results(config_id):
    config = ConfigMap.query.get_or_404(config_id)
    
    # 权限检查
    if not current_user.is_admin:
        if config.server.business_system_id not in [sys.id for sys in current_user.authorized_systems]:
            abort(403)
            
    # 获取最新的结果，按时间倒序
    results = config.diff_results.order_by(DiffResult.created_at.desc()).limit(50).all()
    # 包装成 grouped_results 格式以便复用模板
    return render_template('results.html', grouped_results=[(config, results)])
