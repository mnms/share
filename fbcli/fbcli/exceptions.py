class FbcliBaseError(Exception):
    '''base error for fbcli'''
    def __init__(self, message, *args):
        Exception.__init__(self, message, *args)
        self.message = message

    def __str__(self):
        return self.message

    def class_name(self):
        '''get class name'''
        return self.__class__.__name__


class ConvertError(FbcliBaseError):
    def __init__(self, message, *args):
        FbcliBaseError.__init__(self, message, *args)


class ClusterError(FbcliBaseError):
    def __init__(self, message, *args):
        FbcliBaseError.__init__(self, message, *args)


class PropsKeyError(FbcliBaseError):
    def __init__(self, key, *args):
        message = "{} cannot empty in props".format(key.upper())
        FbcliBaseError.__init__(self, message, *args)


class FileNotExistError(FbcliBaseError):
    def __init__(self, file_path, **kwargs):
        message = "'{}'".format(file_path)
        if 'host' in kwargs.keys():
            host = kwargs['host']
            message = "'{}' at '{}'".format(file_path, host)
        FbcliBaseError.__init__(self, message, *kwargs)


class SSHConnectionError(FbcliBaseError):
    def __init__(self, host, *args):
        message = "SSH connection fail to '{}'".format(host)
        FbcliBaseError.__init__(self, message, *args)


class HostConnectionError(FbcliBaseError):
    def __init__(self, host, *args):
        message = "Host connection fail to '{}'".format(host)
        FbcliBaseError.__init__(self, message, *args)


class HostNameError(FbcliBaseError):
    def __init__(self, host, *args):
        message = "Unknown host name '{}'".format(host)
        FbcliBaseError.__init__(self, message, *args)


class YamlSyntaxError(FbcliBaseError):
    def __init__(self, file_path, *args):
        FbcliBaseError.__init__(self, "'{}'".format(file_path), *args)


class PropsSyntaxError(FbcliBaseError):
    def __init__(self, line, line_number, *args):
        message = "'{}' at line {}".format(line, line_number)
        FbcliBaseError.__init__(self, message, *args)
class SSHCommandError(FbcliBaseError):
    def __init__(self, exit_status, host, command, *args):
        message = "[ExitCode {}] Fail execute command at '{}': {}".format(
            exit_status,
            host,
            command,
        )
        FbcliBaseError.__init__(self, message, *args)
