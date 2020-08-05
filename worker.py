import time
import os
from threading import Thread

from psgd.psgd_training_client import PSGDTraining_Client, PSGDTraining_Parameter_Server
from utils.constants import Initialization_Server, Parameter_Server
from codec.tag import Tag
from utils.log import Logger
from network.communications import Communication_Controller, Worker_Communication_Constructor, get_repr
from utils.models import *

# network agreements in used
from network.starnet_com_process import Worker_Register, Communication_Process, STAR_NET_WORKING_PORTS


CLZ_WORKREGISTER = Worker_Register
CLZ_COM_PROCESS = Communication_Process


def build_tags(node_id: int):
    if not isinstance(node_id, int):
        node_id = int(node_id)

    batch = GlobalSettings.get_default().batch
    blocks = GlobalSettings.get_default().block_assignment.node_2_block[int(node_id)]
    nodes = GlobalSettings.get_default().block_assignment.block_2_node
    tags = [Tag(batch, block, node_id, set(nodes[block])) for block in blocks]

    return tags


class PSGD_Worker:

    def __init__(self):
        self.__running_thread = None
        self.client_logger = Logger(title_info='Worker-{}'.format(get_repr()), log_to_file=True)
        self.__training_log = None

        self.client_logger.log_message('Working started and ready for job submission.')

    def slave_forever(self):
        while True:
            constructor = Worker_Communication_Constructor('0.0.0.0', STAR_NET_WORKING_PORTS, worker_register=Worker_Register())
            try:
                self.client_logger.log_message('Worker started, prepare for connection...')
                register = constructor.buildCom()
                com = Communication_Controller(Communication_Process(register))
                com.establish_communication()

                self.client_logger.log_message('Job submission received. Node assigned node_id({})'.format(com.Node_Id))

                if self.init_PSGD(com):
                    self.do_training(com)

                GlobalSettings.clear_default()
                self.client_logger.log_message('Current session closed, node_id({}).'.format(com.Node_Id))
                time.sleep(10)
                com.close()

            except Exception as e:
                self.client_logger.log_message('Exception occurred: {}'.format(e))

            self.client_logger.log_message('Worker restarting...')
            # wait for safe closure

    def init_PSGD(self, com: Communication_Controller) -> bool:
        self.client_logger.log_message('ACK job submission and request global settings.')
        # initialize global settings
        com.send_one(Initialization_Server, Init.GlobalSettings)
        _, data = com.get_one()
        # restore global settings
        if not isinstance(data, Reply.global_setting_package):
            if data == Reply.I_Need_Your_Working_Log:
                self.client_logger.log_message('Nothing needs to be done, send back logfile and exit process.')
                com.send_one(Initialization_Server, Binary_File_Package(self.client_logger.File_Name))
            return False

        try:
            data.restore()

            self.client_logger.log_message('Request codec and sgd class.')
            # initialize codec and sgd type
            com.send_one(Initialization_Server, Init.Codec_And_SGD_Type)
            _, data = com.get_one()
            # restore
            assert isinstance(data, Reply.codec_and_sgd_package)

            codec, sgd = data.restore()

            self.client_logger.log_message('Request weights and layer type.')
            # initialize weights and layer
            com.send_one(Initialization_Server, Init.Weights_And_Layers)
            _, data = com.get_one()
            # restore
            assert isinstance(data, Reply.weights_and_layers_package)

            layers = data.restore()

            self.client_logger.log_message('Request other stuff.')
            # others
            com.send_one(Initialization_Server, Init.MISC)
            _, data = com.get_one()
            assert isinstance(data, Reply.misc_package)

            loss_t = data.loss_type
            target_acc = data.target_acc
            epoch = data.epoch
            learn_rate = data.learn_rate
            w_type = data.w_types

            self.__training_log = Logger('Training log @ node-{}'.format(com.Node_Id), log_to_file=True)

            if com.Node_Id != Parameter_Server:

                self.client_logger.log_message('Request data samples.')
                # initialize dataset
                com.send_one(Initialization_Server, Init.Samples)
                _, data = com.get_one()
                # restore
                assert isinstance(data, Reply.data_sample_package)

                train_x, train_y, eval_x, eval_y = data.restore()

                self.__running_thread = PSGDTraining_Client(
                    model_init=layers,
                    loss=loss_t,
                    codec_type=codec,
                    sync_class=sgd,
                    com=com,
                    w_types=w_type,
                    tags=build_tags(node_id=com.Node_Id),
                    train_x=train_x,
                    train_y=train_y,
                    eval_x=eval_x,
                    eval_y=eval_y,
                    batch_size=GlobalSettings.get_default().batch.batch_size,
                    epochs=epoch,
                    logger=self.__training_log,
                    learn_rate=learn_rate,
                    target_acc=target_acc
                )
            else:
                self.__running_thread = PSGDTraining_Parameter_Server(
                    model_init=layers,
                    ps_codec=codec,
                    ps_sgd_type=sgd,
                    com=com,
                    w_types=w_type,
                    logger=self.__training_log
                )

            return True
        except Exception as error:
            self.client_logger.log_message('Error encountered while initializing training environment : {}.'.format(error))
            return False

    def do_training(self, com: Communication_Controller):
        self.client_logger.log_message('Prepare to start training process.')
        # check
        assert isinstance(self.__running_thread, Thread)
        assert isinstance(self.__training_log, Logger)

        ready_state = {}
        self.client_logger.log_message('Synchronize timeline with cluster.')

        len_ready = len(com.available_clients())
        for node_id in com.available_clients():
            com.send_one(node_id, Ready_Type())

        # check ready states
        while len(ready_state) != len_ready:
            time.sleep(0.1)
            # require
            n, d = com.get_one()
            if isinstance(d, Ready_Type):
                ready_state[n] = True

        # make output file
        if not os.path.exists('./training'):
            os.mkdir('./training')
        try:
            self.client_logger.log_message('Execution process started.')

            begin = time.time()
            self.__running_thread.start()
            self.__running_thread.join()
            end = time.time()

            self.__training_log.log_message('Execution complete, time:{}'.format(end - begin))
            self.client_logger.log_message('Execution complete, time:{}'.format(end - begin))

            if isinstance(self.__running_thread, PSGDTraining_Client):
                train_csv = Binary_File_Package(self.__running_thread.Trace_Train)
                eval_csv = Binary_File_Package(self.__running_thread.Trace_Eval)

                self.client_logger.log_message('Post training log.')
                com.send_one(Initialization_Server, train_csv)
                com.send_one(Initialization_Server, eval_csv)

        except Exception as error:
            self.client_logger.log_message('Error encountered while executing : {}'.format(error))
            self.__training_log.log_message('Error encountered while executing : {}'.format(error))

        self.client_logger.log_message('Training process exited.')
        log_file = Binary_File_Package(self.__training_log.File_Name)
        com.send_one(Initialization_Server, log_file)


if __name__ == '__main__':
    PSGD_Worker().slave_forever()