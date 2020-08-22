from abc import ABCMeta, abstractmethod
from codec.essential import Block_Weight

class InvalidArguments(Exception):

    def __init__(self, msg, cls):
        self.Msg = msg
        self.Cls = cls

    def to_string(self):
        return "Invalid argument, {}, in class {}.".format(self.Msg, self.Cls)


class netEncapsulation:
    """
        Net Encapsulation, for network transmission.
    """

    def __init__(self, send_to_who:list or int, content:object):

        if isinstance(send_to_who, list):
            self.__target = send_to_who
        elif isinstance(send_to_who, int):
            self.__target = [send_to_who]
        elif isinstance(send_to_who, set):
            self.__target = list(send_to_who)
        else:
            raise InvalidArguments("Send to an unidentified node: {}".format(send_to_who), netEncapsulation)
        if isinstance(content, object):
            self.__packages = content
        else:
            raise InvalidArguments("Package is not required type.", netEncapsulation)


    def target(self):
        return self.__target

    def content(self):
        return self.__packages


def dummy_iterator(func):

    def new_func(*paras):
        rtn = func(*paras)
        if rtn is None:
            for i in []:
                yield None
        elif type(rtn).__name__ == 'generator':
            return rtn
        else:
            yield rtn

    return new_func


class ICommunication_Ctrl(metaclass=ABCMeta):

    def __init__(self):
        self.__updated_weight_buffer = None
        self.__update_complete = False

    @abstractmethod
    def dispose(self):
        """
            Dispose this object and release all the memory.
        :return: None
        """
        pass

    @dummy_iterator
    @abstractmethod
    def update_blocks(self, block_weight:Block_Weight):
        """
            Update the weights generated by a specified block of sample to the cluster,
            function will return a tuple, the first element is the list of node IDs
            of the targets to be sent, the second element is the actual content json to
            be sent.
            Function return None if nothing to be sent.
            When the update process was done, it will check if there were
            enough intermediate values to rebuild full weights.
            such checking will be useless within Synchronized-Stochastic Gradient Descent algorithm.
        :param block_weight: weights generated by a specified block of sample
        :return: None if nothing to sent or NetEncapsulation like : (send target, json object).
        """
        pass

    @dummy_iterator
    @abstractmethod
    def receive_blocks(self, content:object):
        """
            Receive a json like dictionary from cluster.
            decompose the object and check if there were enough intermediate values to
            rebuild full weights.
            Available weights will be saved in self.updated_weight_buffer
        :param content: object, anything send by update_blocks will be received here.
        :return: Generator: for iterating packages to be sent with NetEncapsulation type
                None if nothing need to be sent.
        """
        pass

    def do_something_to_save_yourself(self):
        """
            If SSGD throws a timeout exception, this method will be called.
            This method were implemented intend to break the deadlock among nodes.
        :return: Generator: for iterating packages to be sent with NetEncapsulation type.
        """
        pass

    def is_done(self):
        """
            Check if all the coding and decoding process is done.
        :return: True if done, False if not done.
        """
        return self.__update_complete

    def get_result(self):
        """
            Clear current weights buffer and return.
        :return: weights buffer: ndarray
        """
        assert self.__updated_weight_buffer is not None, 'No weights buffer available.'
        tmp = self.__updated_weight_buffer
        self.__updated_weight_buffer = None
        self.__update_complete = False

        return tmp

    def set_result(self, content):
        """
            Add current delta to old ones
        """
        if self.__updated_weight_buffer is None:
            self.__updated_weight_buffer = content
        else:
            self.__updated_weight_buffer += content

        self.__update_complete = True


class IComPack(metaclass=ABCMeta):

    def deprecated_class(self):
        """
            This interface has been deprecated since ver_0.3 .
            Any codec added after ver_0.3 will not inherit this interface.
        """
        pass
