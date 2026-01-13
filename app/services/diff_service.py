import difflib
from app import db
from app.models import DiffResult, DirectoryDiffResult
from app.services.ssh_service import SSHService
from app.services.gitlab_service import GitLabService
import os
import posixpath # Use posixpath for remote unix paths
from flask import current_app

class DiffService:
    def __init__(self):
        self.gitlab_service = GitLabService()

    def compare_config_map(self, config_map):
        server = config_map.server
        ssh = SSHService(server.ip, server.username, password=server.password, key_path=server.ssh_key_path, port=server.port, os_type=server.os_type)
        
        results = []
        try:
            # 1. 获取服务器文件列表
            # 确保 config_map.remote_path 是以 / 结尾的目录路径，或者处理好拼接
            remote_files = ssh.list_files(config_map.remote_path, config_map.file_pattern)
            # remote_files 包含完整路径
            remote_filenames = [os.path.basename(f) for f in remote_files]
            
            # 2. 获取 GitLab 文件列表
            # 假设 config_map.gitlab_path 是 GitLab 仓库中的目录路径
            gitlab_files = self.gitlab_service.list_files(path=config_map.gitlab_path)
            # GitLab 返回的是 repo 相对路径 (e.g., 'configs/nginx/site.conf')
            
            gitlab_filenames = []
            gitlab_file_map = {} # filename -> full_repo_path
            
            for gf in gitlab_files:
                # 简单的过滤逻辑：只取直接位于 gitlab_path 下的文件，或者根据实际需求调整
                # 这里假设 gitlab_path 是 'configs/nginx'，gf 是 'configs/nginx/site.conf'
                # 我们只关心文件名是否匹配
                name = os.path.basename(gf)
                gitlab_filenames.append(name)
                gitlab_file_map[name] = gf

            # 3. 计算并集
            all_files = set(remote_filenames) | set(gitlab_filenames)
            
            # 清除旧的 DiffResult，只保留最新的
            DiffResult.query.filter_by(config_map_id=config_map.id).delete()
            
            for filename in all_files:
                status = "MATCH"
                diff_text = ""
                
                remote_content = None
                gitlab_content = None
                
                # 获取远程内容
                if filename in remote_filenames:
                    # 使用 posixpath 拼接，确保是 / 分隔符
                    remote_full_path = posixpath.join(config_map.remote_path, filename)
                    remote_content = ssh.read_file(remote_full_path)
                    # 处理可能的 None (读取失败)
                    if remote_content is None:
                        # 这种情况可能是权限问题或文件刚刚消失
                        pass
                
                # 获取 GitLab 内容
                if filename in gitlab_filenames:
                    gitlab_content = self.gitlab_service.get_file_content(gitlab_file_map[filename])
                
                # 比较
                if remote_content is None and gitlab_content is None:
                    continue # 应该不会发生
                elif remote_content is None:
                    status = "MISSING_REMOTE"
                elif gitlab_content is None:
                    status = "MISSING_LOCAL"
                else:
                    # 使用 splitlines() 预处理，忽略换行符差异 (\r\n vs \n)
                    remote_lines = remote_content.splitlines()
                    gitlab_lines = gitlab_content.splitlines()
                    
                    if remote_lines != gitlab_lines:
                        status = "DIFF"
                        diff = difflib.unified_diff(
                            gitlab_lines,
                            remote_lines,
                            fromfile=f'GitLab/{filename}',
                            tofile=f'Server/{filename}',
                            lineterm=''
                        )
                        diff_text = '\n'.join(list(diff))
                    else:
                        status = "MATCH"
                
                # 保存结果
                result = DiffResult(
                    config_map_id=config_map.id,
                    file_name=filename,
                    status=status,
                    diff_content=diff_text
                )
                db.session.add(result)
                results.append(result)
                
            db.session.commit()
            
        except Exception as e:
            if current_app:
                current_app.logger.info(f"Error comparing config map {config_map.id}: {e}")
            db.session.rollback()
            raise # 抛出异常以便上层知道失败了
        finally:
            ssh.close()
            
        return results
    
    def compare_directory_pair(self, pair):
        left_ssh = SSHService(pair.left_server.ip, pair.left_server.username, password=pair.left_server.password, key_path=pair.left_server.ssh_key_path, port=pair.left_server.port, os_type=pair.left_server.os_type)
        right_ssh = SSHService(pair.right_server.ip, pair.right_server.username, password=pair.right_server.password, key_path=pair.right_server.ssh_key_path, port=pair.right_server.port, os_type=pair.right_server.os_type)
        
        results = []
        try:
            left_files = left_ssh.list_files(pair.left_path, pair.file_pattern)
            right_files = right_ssh.list_files(pair.right_path, pair.file_pattern)
            
            left_names = {os.path.basename(p): p for p in left_files}
            right_names = {os.path.basename(p): p for p in right_files}
            
            all_names = set(left_names.keys()) | set(right_names.keys())
            
            DirectoryDiffResult.query.filter_by(pair_id=pair.id).delete()
            
            for name in all_names:
                status = "MATCH"
                diff_text = ""
                left_content = None
                right_content = None
                
                if name in left_names:
                    left_content = left_ssh.read_file(left_names[name])
                if name in right_names:
                    right_content = right_ssh.read_file(right_names[name])
                
                if left_content is None and right_content is None:
                    continue
                elif left_content is None:
                    status = "MISSING_LEFT"
                elif right_content is None:
                    status = "MISSING_RIGHT"
                else:
                    left_lines = left_content.splitlines()
                    right_lines = right_content.splitlines()
                    if left_lines != right_lines:
                        status = "DIFF"
                        diff = difflib.unified_diff(
                            left_lines,
                            right_lines,
                            fromfile=f'Left/{name}',
                            tofile=f'Right/{name}',
                            lineterm=''
                        )
                        diff_text = '\n'.join(list(diff))
                    else:
                        status = "MATCH"
                
                result = DirectoryDiffResult(
                    pair_id=pair.id,
                    file_name=name,
                    status=status,
                    diff_content=diff_text,
                    left_content=left_content,  # Save original content
                    right_content=right_content # Save original content
                )
                db.session.add(result)
                results.append(result)
            
            db.session.commit()
        except Exception as e:
            if current_app:
                current_app.logger.info(f"Error comparing directory pair {pair.id}: {e}")
            db.session.rollback()
            raise
        finally:
            left_ssh.close()
            right_ssh.close()
        
        return results
