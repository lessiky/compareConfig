import gitlab
from flask import current_app
import base64

class GitLabService:
    def __init__(self):
        self.url = current_app.config['GITLAB_URL']
        self.token = current_app.config['GITLAB_TOKEN']
        self.project_id = current_app.config['GITLAB_PROJECT_ID']
        self.gl = None
        self.project = None

    def connect(self):
        if self.project:
            return

        try:
            self.gl = gitlab.Gitlab(self.url, private_token=self.token)
            # self.gl.auth() # auth() call is optional if private_token is provided, but good for check
            self.project = self.gl.projects.get(self.project_id)
        except Exception as e:
            current_app.logger.error(f"GitLab connection failed: {e}")
            raise

    def get_file_content(self, file_path, ref='main'):
        """获取文件内容，返回字符串"""
        self.connect()
        
        try:
            f = self.project.files.get(file_path=file_path, ref=ref)
            data = f.decode()
            if isinstance(data, bytes):
                for enc in ('utf-8', 'gb18030', 'gbk', 'utf-16-le', 'latin-1'):
                    try:
                        return data.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return data.decode('utf-8', errors='replace')
            return data
        except gitlab.exceptions.GitlabGetError:
            # print(f"File not found in GitLab: {file_path}")
            return None
        except Exception as e:
            current_app.logger.error(f"Error getting file from GitLab: {e}")
            return None

    def update_file(self, file_path, content, commit_message, ref='main'):
        """更新或创建文件"""
        self.connect()
        
        try:
            # 尝试获取文件，如果存在则更新，不存在则创建
            try:
                f = self.project.files.get(file_path=file_path, ref=ref)
                f.content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                f.save(branch=ref, commit_message=commit_message, encoding='base64')
                return True, "Updated successfully"
            except gitlab.exceptions.GitlabGetError:
                # 文件不存在，创建
                self.project.files.create({
                    'file_path': file_path,
                    'branch': ref,
                    'content': content,
                    'commit_message': commit_message
                })
                return True, "Created successfully"
                
        except Exception as e:
            return False, str(e)

    def list_files(self, path='.', ref='main', recursive=False):
        """列出指定目录下的文件"""
        self.connect()
        
        try:
            items = self.project.repository_tree(path=path, ref=ref, recursive=recursive, all=True)
            # 过滤只返回文件
            files = [item['path'] for item in items if item['type'] == 'blob']
            return files
        except Exception as e:
            current_app.logger.error(f"Error listing files from GitLab: {e}")
            return []
