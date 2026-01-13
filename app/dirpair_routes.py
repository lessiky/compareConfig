from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from app import db
from app.models import DirectoryPair, Server, DirectoryDiffResult
from app.services.diff_service import DiffService

bp = Blueprint('dirpair', __name__)

@bp.before_request
@login_required
def require_login():
    pass

@bp.route('/dirpairs')
def list_pairs():
    if current_user.is_admin:
        pairs = DirectoryPair.query.all()
        servers = Server.query.all()
    else:
        pairs = DirectoryPair.query.filter_by(user_id=current_user.id).all()
        system_ids = [sys.id for sys in current_user.authorized_systems]
        servers = Server.query.filter(Server.business_system_id.in_(system_ids)).all()
    return render_template('dirpair/list.html', pairs=pairs, servers=servers)

@bp.route('/dirpairs/add', methods=['POST'])
def add_pair():
    name = request.form.get('name')
    left_server_id = request.form.get('left_server_id')
    left_path = request.form.get('left_path')
    right_server_id = request.form.get('right_server_id')
    right_path = request.form.get('right_path')
    file_pattern = request.form.get('file_pattern', '*')
    
    if not name or not left_server_id or not left_path or not right_server_id or not right_path:
        flash('请完整填写目录比对信息', 'danger')
        return redirect(url_for('dirpair.list_pairs'))
    
    left_server = Server.query.get_or_404(left_server_id)
    right_server = Server.query.get_or_404(right_server_id)
    
    if not current_user.is_admin:
        allowed_ids = [sys.id for sys in current_user.authorized_systems]
        if left_server.business_system_id not in allowed_ids or right_server.business_system_id not in allowed_ids:
            abort(403)
    
    pair = DirectoryPair(
        name=name,
        left_server_id=left_server_id,
        left_path=left_path,
        right_server_id=right_server_id,
        right_path=right_path,
        file_pattern=file_pattern,
        user_id=current_user.id
    )
    db.session.add(pair)
    db.session.commit()
    flash('目录比对关系创建成功', 'success')
    return redirect(url_for('dirpair.list_pairs'))

@bp.route('/dirpairs/compare/batch', methods=['POST'])
def batch_compare():
    pair_ids = request.form.getlist('pair_ids')
    if not pair_ids:
        flash('请至少选择一个比对关系', 'warning')
        return redirect(url_for('dirpair.list_pairs'))
        
    service = DiffService()
    success_count = 0
    fail_count = 0
    
    processed_ids = []
    for pid in pair_ids:
        pair = DirectoryPair.query.get(pid)
        if not pair:
            continue
            
        # 权限检查
        if not current_user.is_admin and pair.user_id != current_user.id:
            continue
            
        try:
            service.compare_directory_pair(pair)
            success_count += 1
            processed_ids.append(str(pid))
        except Exception as e:
            current_app.logger.error(f"Error comparing pair {pid}: {e}")
            fail_count += 1
            
    if success_count > 0:
        flash(f'成功执行 {success_count} 个比对任务', 'success')
    if fail_count > 0:
        flash(f'{fail_count} 个比对任务执行失败', 'danger')
        
    if processed_ids:
        ids_str = ','.join(processed_ids)
        return redirect(url_for('dirpair.view_batch_results', ids=ids_str))
        
    return redirect(url_for('dirpair.list_pairs'))

@bp.route('/dirpairs/results/batch')
def view_batch_results():
    ids_str = request.args.get('ids', '')
    if not ids_str:
        return redirect(url_for('dirpair.list_pairs'))
        
    pair_ids = [int(x) for x in ids_str.split(',') if x.isdigit()]
    
    # 获取所有选中的 pair 的结果
    pairs = DirectoryPair.query.filter(DirectoryPair.id.in_(pair_ids)).all()
    
    # 过滤权限
    if not current_user.is_admin:
        pairs = [p for p in pairs if p.user_id == current_user.id]
        
    grouped_results = []
    for p in pairs:
        # 获取最新的结果 (假设比对刚刚完成，取最新的那一批)
        # 这里为了简化，我们取最近一次运行产生的所有结果
        # 更严谨的做法可能是通过 batch_id 或 timestamp 过滤
        res = DirectoryDiffResult.query.filter_by(pair_id=p.id).order_by(DirectoryDiffResult.created_at.desc()).all()
        if res:
            grouped_results.append((p, res))
            
    return render_template('dirpair/batch_results.html', grouped_results=grouped_results)

@bp.route('/dirpairs/compare/<int:id>')
def compare_pair(id):
    pair = DirectoryPair.query.get_or_404(id)
    if not current_user.is_admin and pair.user_id != current_user.id:
        abort(403)
    service = DiffService()
    try:
        service.compare_directory_pair(pair)
        flash('目录比对完成', 'success')
    except Exception as e:
        flash(f'目录比对失败: {e}', 'danger')
    return redirect(url_for('dirpair.view_results', id=id))

@bp.route('/dirpairs/results/<int:id>')
def view_results(id):
    pair = DirectoryPair.query.get_or_404(id)
    if not current_user.is_admin and pair.user_id != current_user.id:
        abort(403)
    results = DirectoryDiffResult.query.filter_by(pair_id=id).order_by(DirectoryDiffResult.created_at.desc()).all()
    return render_template('dirpair/results.html', pair=pair, results=results)

@bp.route('/dirpairs/delete/<int:id>', methods=['POST'])
def delete_pair(id):
    pair = DirectoryPair.query.get_or_404(id)
    if not current_user.is_admin and pair.user_id != current_user.id:
        abort(403)
    DirectoryDiffResult.query.filter_by(pair_id=id).delete()
    db.session.delete(pair)
    db.session.commit()
    flash('目录比对关系已删除', 'success')
    return redirect(url_for('dirpair.list_pairs'))
