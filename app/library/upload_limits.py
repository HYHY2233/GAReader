from django.core.files.uploadhandler import FileUploadHandler, StopUpload

class LimitedUploadHandler(FileUploadHandler):
    def __init__(self, request=None):
        super().__init__(request)
        self.total = 0
    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.size = 0
        self.limit = {'html': 50, 'pdf': 100, 'mapping': 5}.get(self.field_name, 0) * 1024**2
    def receive_data_chunk(self, raw_data, start):
        self.size += len(raw_data)
        self.total += len(raw_data)
        if self.size > self.limit or self.total > 155 * 1024**2:
            self.request.upload_limit_error = True
            raise StopUpload(connection_reset=False)
        return raw_data
    def file_complete(self, file_size): return None
