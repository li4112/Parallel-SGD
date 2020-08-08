# 教程

　　本段教您如何创建一个 P-SGD 编码传输控制器， P-SGD 编码控制器是 P-SGD 的
核心组件，负责控制两个神经网络层（Layer）的参数同步过程。编码控制器仅需要控制
一层网络的权重交互，P-SGD Worker 在初始化运行环境之前会为每个神经网络层的每个
参数创建一个编码控制器，P-SGD Transfer 会保证每个编码控制器接收到的权重总是来
自同一个神经网络层（无论这段数据是来源于本机还是其他 Worker，P-SGD Transfer
总是保证将其转发给唯一的编码控制器）。

## 注解

### 关键词
　　文中提到了一些关键词，其对应的含义如下表：

|名字|对应类（实体）|描述|
|----|----|----|
|P-SGD Transfer|psgd.interfaces.ITransfer|与神经网络 Optimizer 直接互操作的接口，包含 put_weights 和 get_weights 方法|
|ISync-SGD|psgd.interfaces.IParallelSGD|P-SGD Transfer 中的子控制器，每个 ISync-SGD 掌管着一个权重参数的分布式交互策略|
|Async-SGD|psgd.asgd.AsynchronizedSGD|ISync-SGD 的一个实现，使用异步策略执行节点之间的数据更新|

### 文献
　　关于 Async-SGD 的其他细节，请参考文献：  
　　Recht, Benjamin and Re, Christopher and Wright, Stephen and Feng Niu. Hogwild: A Lock-Free Approach to Parallelizing Stochastic Gradient Descent. Advances in Neural Information Processing Systems (NIPS). Curran Associates, Inc. 2011.

### Warning

　　**注意**：本测试器只测试类的完整性，并不会测试编码过程的统计有效性，您需要使用数学证明来确认您的编码过程是完整有效的。

## 接口

　　编码控制器继承自 codec.interfaces.ICommunication_Ctrl 抽象类，当需要创建
新的编码控制器时，需要继承自抽象类，抽象类负责了参数提交与更新的判断。P-SGD Transfer
保证了对编码器的调用是串行化的，所以无需在编码控制器中考虑并行因素的影响。  
　　运行以下代码导入编码控制器抽象。

```python
from codec.interfaces import ICommunication_Ctrl
```

## 参数

　　编码控制器总是需要接受一个 node_id 来创建，当需要创建编码控制器时，P-SGD Transfer 会
创建编码控制器并给一个 node_id 的参数，代表了当前节点在集群中的唯一识别编号。  
　　您可以选择接受并记录该参数，也可以选择抛弃该参数，该参数只会在创建的时候传递，之后也没有
与该参数关联的接口，无需做过多的处理。

```python
from codec.interfaces import ICommunication_Ctrl

class myComCtrl(ICommunication_Ctrl):
    def __init__(self, node_id):
        super().__init__()
        # save it if you need it
        self.__node_id = node_id
```

## 处理资源释放

　　当 P-SGD Transfer 终止一个编码控制器的生命周期时，调用 dispose() 接口执行释放，需要在
您的类中实现该接口以正确配置资源释放。

```python
from codec.interfaces import ICommunication_Ctrl

class myComCtrl(ICommunication_Ctrl):
    def __init__(self, node_id):
        super().__init__()
        # save it if you need it
        self.__node_id = node_id
    
    def dispose(self):
        print('my communication controller is disposed.')
```

## 处理数据

　　现在我们已经配置好了对象的构造与释放方法，下面就可以实现核心内容了，即如何处理数据。发送给
编码控制器的数据总是有两个来源，一个是由本机提交，另一个是从其他计算节点获取，分别对应两个接口：
update_blocks(self, block_weight) 和 receive_blocks(self, json_dict)。  

### 数据的提交

　　当本机提交计算完成的权重时，P-SGD Transfer 会将事件转发给对应层的编码控制器，其中 block_weight
是 codec.essential.Block_Weight 的对象，保存了本机能够获取到的与该参数关联的信息。其中有：  

| 成员 | 类型 | 注释 |
| ---- | ---- | ---- |
| Layer_ID | int | 本参数的层编号 |
|Batch_ID|int|本参数的批次编号|
|Block_ID|int|本参数的样本Block编号|
|Company_ID|sequence|本参数对应的样本Block还在哪些节点上出现过|
|Adversary_ID|sequence|本参数对应的样本Block没在哪些节点上出现过|
|Content|numpy.ndarray|参数本身|

**注意**：传入的参数默认是权重梯度而不是权重，要使用参数更新机制，需要更换 P-SGD Optimizer，
Optimizer 可在 server_util.init_model.__optimizer_map 中找到。  

　　下面的代码接收了梯度平均化方法的参数提交：
```python
from codec.interfaces import ICommunication_Ctrl
from codec.essential import Block_Weight

class myComCtrl(ICommunication_Ctrl):
    def __init__(self, node_id):
        super().__init__()
        # save it if you need it
        self.__node_id = node_id
    
    def dispose(self):
        print('my communication controller is disposed.')

    def update_blocks(self, block_weight:Block_Weight):
        print('Weights delta received.')
        print('from block: {}'.format(block_weight.Block_ID))
        print('has content: {}'.format(block_weight.Content))
```

　　当您需要将数据发送到网络上时，您需要几个特别的参数。首先，您需要知道您的数据要送给
哪些节点。要获取全局已申请的节点编号，调用以下代码：
```python
from profiles.settings import GlobalSettings

print('Workers in current job: {}'.format(GlobalSettings.get_default().nodes))
```

　　其次，您需要知道在 P-SGD Transfer 中允许传输的数据类型是什么。P-SGD Transfer 对象
之间允许交互的类型是 dict ，您需要将您的数据封装至 dict 中，编码控制器是第一个产生 dict 
对象的类，因此，您需要新建一个 dict 对象。  
　　要将其返回给 P-SGD Transfer 处理，您还需要将其封装成 netEncapsulation 对象。
依照梯度平均化编码控制器的任务提交逻辑，应当将本节点计算所得的梯度传输给参数服
务器或其他没有该数据的执行节点，我们先实现一个无参数服务器的简单模型，代码如下：
```python
from codec.interfaces import ICommunication_Ctrl
from codec.essential import Block_Weight
from codec.interfaces import netEncapsulation

class myComCtrl(ICommunication_Ctrl):
    def __init__(self, node_id):
        super().__init__()
        # save it if you need it
        self.__node_id = node_id
    
    def dispose(self):
        print('my communication controller is disposed.')

    def update_blocks(self, block_weight:Block_Weight):
        print('Weights delta received.')
        print('from block: {}'.format(block_weight.Block_ID))
        print('has content: {}'.format(block_weight.Content))
        
        send_to = block_weight.Adversary_ID
        pkg = {
            'data': block_weight.Content
        }
        
        yield netEncapsulation(send_to, pkg)
```

**注意**：update_block 和 receive_blocks 都返回迭代器对象，当有多个数据包需要发送
的时候，使用 yield 逐个生成，当无数据包需要发送的时候，可以返回 None。

　　至此，我们就完成了将数据送至网络的过程，生成好数据包后，您的数据包会被 ISync-SGD
获取并进行时效性编号，并交由 P-SGD Transfer 进行转发，P-SGD Transfer 获取并将数据包放置到
ICommunication_Control 的发送队列，当发送连接可用时，您的数据会被序列化并发送给指
定的节点。

### 数据的接收

　　当接收到其他工作节点的数据时，P-SGD Transfer 会将事件转发给对应的编码器控制层，
由 ISync-SGD 决定是否将该事件转发给编码控制器，SSGD 会将数据保留直到下一次全局更新
开始时才会将数据转发给编码控制器，ASGD 则会在每次数据到达时直接将数据转发给编码控制器。
选择合适的 ISync-SGD 类型，使得您的编码控制器能够有效的运作。（参考 [主页](../README.md)
了解如何从参数配置 SGD-Type）  
　　当您完成一批数据的处理时，调用 set_result 方法来提交您的结果，当神经网络端需要
更新权值时，会调用 get_result 方法直接获取数据，如果获取不到数据则会进行超时计数，
超过一个 SynchronizedSGD.INT_READ_TIMEOUT_MS 周期后，ISync-SGD 会尝试调用编码器的
do_something_to_save_yourself 方法试图恢复集群的稳定状态，当超出两个 SynchronizedSGD.INT_READ_TIMEOUT_MS 
周期后，P-SGD Transfer 就会报告超时错误，与集群的连接就会断开。  
　　当有消息需要处理时，P-SGD Transfer 会调用 receive_blocks 方法，实现该方法并与
您的 update_blocks 匹配，就可以完成一次任务的转发。要注意的是，节点不一定会在接收消息的
时候完成参数的归一，可能会有其他比较快的计算节点抢先完成计算，本节点在自己计算完成并提交
之后才完成参数的归一，因此我们要在参数提交和参数接收两个方法中都定义归一操作。利用全局
节点总数来判断我们是否需要进行梯度平均化操作，实现如下：  
```python
from codec.interfaces import ICommunication_Ctrl
from codec.essential import Block_Weight
from codec.interfaces import netEncapsulation

from profiles.settings import GlobalSettings


class myComCtrl(ICommunication_Ctrl):
    def __init__(self, node_id):
        super().__init__()
        # 保存并记录本节点编号信息，除此之外再也没有其他地方可以获取该信息
        self.__node_id = node_id
        # 保存并记录当前批次已经收到了多少份结果
        self.__global_weights = 0
        self.__current_recv = 0

    def __do_grad_average(self):
        how_much_nodes = GlobalSettings.get_default().node_count
        if self.__current_recv == how_much_nodes:
            # 执行梯度平均
            self.set_result(self.__global_weights / how_much_nodes)
            # 重设梯度值，等待下一批次的循环
            self.__global_weights = 0
            self.__current_recv = 0
```
  
　　如果当前的节点工作的比其他节点快，那么当前节点就会在接收到其他节点发来的消息时完成梯度
平均化，如果当前的节点工作的比其他节点慢，那么当前节点需要在完成本地更新之后完成梯度平均化。因此我们
在 update_blocks 方法和 receive_blocks 方法中都调用了梯度平均化判断。  
　　完整的代码如下：

```python
from codec.interfaces import ICommunication_Ctrl
from codec.essential import Block_Weight
from codec.interfaces import netEncapsulation

from profiles.settings import GlobalSettings


class myComCtrl(ICommunication_Ctrl):
    def __init__(self, node_id):
        super().__init__()
        # 保存并记录本节点编号信息，除此之外再也没有其他地方可以获取该信息
        self.__node_id = node_id
        self.__global_weights = 0
        self.__current_recv = 0
    
    def dispose(self):
        print('my communication controller is disposed.')

    def update_blocks(self, block_weight:Block_Weight):
        print('Weights delta received.')
        print('from block: {}'.format(block_weight.Block_ID))
        print('It has a content with shape: {}'.format(block_weight.Content.shape))
        
        # 获取没有该数据的节点
        send_to = block_weight.Adversary_ID
        # 我们使用 'data' 字符串来标记我们的梯度内容
        pkg = {
            'data': block_weight.Content
        }
        # 记录本机梯度
        self.__global_weights += block_weight.Content
        self.__current_recv += 1
        # 检查是否接受完所有数据
        self.__do_grad_average()
        # 发送梯度
        yield netEncapsulation(send_to, pkg)

    def receive_blocks(self, json_dict:dict):
        print('I have received an package.')
        print('It has a content with shape: {}'.format(json_dict['data'].shape))
        # 我们使用上述定义的 'data' 字符串获取我们更新的梯度内容
        self.__global_weights += json_dict['data']
        # 记录已经接收到多少个梯度了
        self.__current_recv += 1
        # 检查是否接受完所有数据
        self.__do_grad_average()
        
    def __do_grad_average(self):
        how_much_nodes = GlobalSettings.get_default().node_count
        if self.__current_recv == how_much_nodes:
            # 执行梯度平均
            self.set_result(self.__global_weights / how_much_nodes)
            # 重设梯度值，等待下一批次的循环
            self.__global_weights = 0
            self.__current_recv = 0
```

**注意**：在 Async-SGD 执行模式下，数据的产生与接收是异步的，update_blocks 与 receive_blocks
方法可能会同时被不同的线程调用，需要额外考虑数据的线程安全性。


## 调试

　　完成了编码控制器的编写后，我们需要对编码控制器进行 DEBUG，直接将其放入分布式集群
进行测试肯定不是一个好的选择。codec.test_codec 中提供了不同类型的自动化测试脚本，
在上述教程中我们编写了一个梯度平均化编码控制器，且不使用参数服务器，那么现在使用
codec.test_codec.p2p_test_script.py 执行一下编码控制器的测试。  
　　找到测试脚本的第 11-22 行，用我们编写的编码控制器替换掉原有的配置，使用您的IDE进行
DEBUG 或 RUN 该脚本，如果未出现错误，则证明该编码控制器在同步环境下是可用的。（注意：
异步环境下的线程安全性问题比较隐蔽且难以探查，需要异步编码控制器时您应当反复检查其线程
安全性，不安全的代码可能会导致意想不到的效果）  
　　假设我们的编码控制器配置在文件 codec.tutorial_codec.py 中，要修改的内容如下：

```python
# more codes upon .......

"""
    ---------------DEFINE HERE---------------
"""
# import test codec
from codec.tutorial_codec import myComCtrl
from profiles.blockassignment.duplicate import DuplicateAssignment
# Type
SLAVE_CODEC = myComCtrl
ASSIGNMENTS = DuplicateAssignment
"""
    ---------------DEFINE HERE---------------
"""

# more codes below ......
```
## 其他
　　关于分配策略（IBlockAssignment）的详情，请参阅 [分配策略](../profiles/blockassignment/README.md)。
