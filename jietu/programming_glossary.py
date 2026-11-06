"""Offline programming vocabulary for OCR whole-input matching.

Entries are intentionally conservative: API names retain their documented spelling,
and SQL meanings are dialect-sensitive where noted.  All lookup keys are lower-case.
"""


def _table(text: str) -> dict[str, str]:
    """Turn the compact, reviewable vocabulary tables into dictionaries."""
    result: dict[str, str] = {}
    for row in text.splitlines():
        row = row.strip()
        if row and not row.startswith("#"):
            key, value = row.split("|", 1)
            result[key.strip().lower()] = value.strip()
    return result


PYTHON_TERMS = _table(r"""
and|Python 逻辑与关键字
as|Python 别名绑定关键字
assert|Python 断言语句
async|Python 异步定义关键字
await|Python 等待异步结果关键字
break|Python 跳出循环关键字
case|Python match 分支关键字
class|Python 类定义关键字
continue|Python 继续循环关键字
def|Python 函数定义关键字
del|Python 删除绑定关键字
elif|Python 条件分支关键字
else|Python 否则分支关键字
except|Python 异常捕获关键字
False|Python 布尔假值
finally|Python 异常清理分支
for|Python for 迭代关键字
from|Python 导入来源关键字
global|Python 全局绑定声明
if|Python 条件关键字
import|Python 模块导入关键字
in|Python 成员或迭代关键字
is|Python 对象身份比较关键字
lambda|Python 匿名函数关键字
match|Python 结构化匹配关键字
None|Python 空值对象
nonlocal|Python 闭包外层绑定声明
not|Python 逻辑非关键字
or|Python 逻辑或关键字
pass|Python 空操作语句
raise|Python 抛出异常关键字
return|Python 函数返回关键字
True|Python 布尔真值
try|Python 异常处理起始关键字
while|Python while 循环关键字
with|Python 上下文管理关键字
yield|Python 生成器产出关键字
abs|Python 绝对值内置函数
aiter|Python 异步迭代器内置函数
all|Python 全部为真内置函数
any|Python 任一为真内置函数
anext|Python 异步取下一项函数
ascii|Python ASCII 转义表示函数
bin|Python 二进制字符串函数
bool|Python 布尔转换函数
breakpoint|Python 调试断点内置函数
bytearray|Python 可变字节数组类型
bytes|Python 不可变字节序列类型
callable|Python 可调用性检查函数
chr|Python Unicode 码点转字符
classmethod|Python 类方法装饰器
compile|Python 编译源码函数
complex|Python 复数类型构造器
delattr|Python 删除属性函数
dict|Python 字典类型构造器
dir|Python 对象属性列表函数
divmod|Python 商和余数函数
enumerate|Python 带索引迭代函数
eval|Python 表达式求值函数
exec|Python 执行代码函数
filter|Python 过滤迭代器函数
float|Python 浮点类型构造器
format|Python 格式化函数
frozenset|Python 不可变集合类型
getattr|Python 读取属性函数
globals|Python 全局命名空间函数
hasattr|Python 属性存在性检查
hash|Python 哈希值函数
help|Python 帮助信息函数
hex|Python 十六进制字符串函数
id|Python 对象身份编号函数
input|Python 标准输入函数
int|Python 整数类型构造器
isinstance|Python 实例类型检查函数
issubclass|Python 子类关系检查函数
iter|Python 创建迭代器函数
len|Python 序列长度函数
list|Python 列表类型构造器
locals|Python 局部命名空间函数
map|Python 映射迭代器函数
max|Python 最大值函数
memoryview|Python 缓冲区视图类型
min|Python 最小值函数
next|Python 取迭代器下一项函数
object|Python 对象基类
oct|Python 八进制字符串函数
open|Python 文件打开函数
ord|Python 字符转 Unicode 码点
pow|Python 幂运算函数
print|Python 标准输出函数
property|Python 属性描述器
range|Python 整数范围对象
repr|Python 可读对象表示函数
reversed|Python 反向迭代器函数
round|Python 舍入函数
set|Python 集合类型构造器
setattr|Python 设置属性函数
slice|Python 切片对象构造器
sorted|Python 排序列表函数
staticmethod|Python 静态方法装饰器
str|Python 字符串类型构造器
sum|Python 求和函数
super|Python 父类代理对象
tuple|Python 元组类型构造器
type|Python 类型对象或动态构造器
vars|Python 对象属性字典函数
zip|Python 并行聚合迭代器
__init__|Python 初始化方法
__name__|Python 模块或类名称属性
__main__|Python 主模块名称
__all__|Python 模块公开导出列表
__doc__|Python 文档字符串属性
__file__|Python 模块文件路径属性
__package__|Python 模块包名属性
_private|Python 常见私有命名约定
exception|Python 异常统称
baseexception|Python 异常层次根类
exceptiongroup|Python 异常组
stopiteration|Python 迭代结束异常
stopasynciteration|Python 异步迭代结束异常
arithmeticerror|Python 算术错误基类
floatingpointerror|Python 浮点运算错误
overflowerror|Python 数值溢出异常
zerodivisionerror|Python 除零异常
assertionerror|Python 断言失败异常
attributeerror|Python 属性访问异常
buffererror|Python 缓冲区异常
eoferror|Python 输入结束异常
importerror|Python 导入失败异常
modulenotfounderror|Python 模块未找到异常
indexerror|Python 序列下标异常
keyerror|Python 字典键不存在异常
memoryerror|Python 内存分配异常
nameerror|Python 名称未定义异常
unboundlocalerror|Python 局部变量未绑定异常
oserror|Python 操作系统错误基类
filenotfounderror|Python 文件不存在异常
permissionerror|Python 权限异常
processlookuperror|Python 进程不存在异常
timeouterror|Python 超时异常
referenceerror|Python 弱引用失效异常
runtimeerror|Python 运行时错误基类
notimplementederror|Python 未实现异常
recursionerror|Python 递归深度异常
syntaxerror|Python 语法错误异常
indentationerror|Python 缩进错误异常
taberror|Python 制表符缩进异常
systemerror|Python 解释器内部错误
systemexit|Python 退出异常
typeerror|Python 类型错误异常
valueerror|Python 值格式异常
unicodeerror|Python Unicode 错误基类
unicodeencodeerror|Python Unicode 编码异常
unicodedecodeerror|Python Unicode 解码异常
unicodetranslateerror|Python Unicode 转换异常
warning|Python 警告基类
userwarning|Python 用户警告
runtimewarning|Python 运行时警告
futurewarning|Python 未来行为警告

# 常用模块与类型
os|Python 操作系统接口模块
sys|Python 解释器运行时模块
re|Python 正则表达式模块
json|Python JSON 编解码模块
math|Python 数学函数模块
statistics|Python 统计函数模块
random|Python 随机数模块
datetime|Python 日期时间模块
time|Python 时间模块
pathlib|Python 面向对象路径模块
subprocess|Python 子进程模块
threading|Python 线程模块
multiprocessing|Python 多进程模块
asyncio|Python 异步 IO 模块
logging|Python 日志模块
unittest|Python 单元测试框架
pytest|常见 Python 测试工具（第三方）
dataclasses|Python 数据类模块
typing|Python 类型标注模块
collections|Python 容器扩展模块
itertools|Python 迭代工具模块
functools|Python 函数工具模块
contextlib|Python 上下文工具模块
abc|Python 抽象基类模块
enum|Python 枚举模块
copy|Python 对象复制模块
csv|Python CSV 模块
sqlite3|Python SQLite 数据库模块
http|Python HTTP 包
socket|Python 网络套接字模块

# 标准 API（点号名称保留原 API）
os.path.join|Python 拼接文件路径
os.path.exists|Python 检查路径存在
os.path.basename|Python 取得路径文件名
os.path.dirname|Python 取得路径目录名
os.path.abspath|Python 取得绝对路径
os.path.splitext|Python 分离扩展名
pathlib.Path|Python 路径对象类型
pathlib.Path.exists|Python 路径存在检查
pathlib.Path.mkdir|Python 创建目录方法
pathlib.Path.read_text|Python 读取文本文件方法
pathlib.Path.write_text|Python 写入文本文件方法
json.loads|Python JSON 字符串解析
json.dumps|Python 对象序列化为 JSON
re.search|Python 正则搜索
re.match|Python 正则起始匹配
re.findall|Python 正则查找全部
re.sub|Python 正则替换
str.split|Python 字符串分割方法
str.join|Python 字符串连接方法
str.strip|Python 去除首尾空白方法
str.replace|Python 字符串替换方法
str.startswith|Python 前缀判断方法
str.endswith|Python 后缀判断方法
list.append|Python 列表追加方法
list.extend|Python 列表批量追加方法
list.insert|Python 列表插入方法
list.pop|Python 列表移除并返回方法
dict.get|Python 字典安全取值方法
dict.items|Python 字典键值迭代方法
dict.keys|Python 字典键迭代方法
dict.values|Python 字典值迭代方法
set.add|Python 集合添加方法
set.discard|Python 集合安全删除方法
logging.getLogger|Python 获取日志记录器
logging.basicConfig|Python 配置基础日志
asyncio.run|Python 运行异步协程
unittest.TestCase|Python 单元测试基类
""")

JAVA_TERMS = _table(r"""
abstract|Java 抽象类或方法修饰符
assert|Java 断言语句
boolean|Java 布尔基本类型
break|Java 跳出循环语句
byte|Java 8 位整数类型
case|Java switch 分支标签
catch|Java 异常捕获块
char|Java 16 位字符类型
class|Java 类定义关键字
const|Java 保留关键字（不可使用）
continue|Java 继续循环语句
default|Java 默认分支或接口默认方法
do|Java do-while 循环关键字
double|Java 双精度浮点类型
else|Java 否则分支
enum|Java 枚举类型
extends|Java 类继承关键字
final|Java 不可重新赋值或覆写修饰符
finally|Java 异常清理块
float|Java 单精度浮点类型
for|Java for 循环
if|Java 条件语句
implements|Java 类实现接口关键字
import|Java 导入类型或成员
instanceof|Java 类型兼容性检查运算符
int|Java 32 位整数类型
interface|Java 接口定义关键字
long|Java 64 位整数类型
native|Java 本地方法修饰符
new|Java 创建对象关键字
package|Java 包声明关键字
private|Java 私有访问修饰符
protected|Java 受保护访问修饰符
public|Java 公共访问修饰符
return|Java 返回语句
short|Java 16 位整数类型
static|Java 类级成员修饰符
strictfp|Java 严格浮点修饰符
super|Java 父类引用关键字
switch|Java 多分支选择语句
synchronized|Java 监视器同步修饰符
this|Java 当前对象引用
throw|Java 抛出异常语句
throws|Java 方法异常声明
transient|Java 序列化忽略字段修饰符
try|Java 异常处理块
void|Java 无返回值类型
volatile|Java 跨线程可见字段修饰符
while|Java while 循环
var|Java 局部变量类型推断（Java 10+）
yield|Java switch 表达式产出（Java 14+）
record|Java 数据载体类（Java 16+）
sealed|Java 密封类修饰符（Java 17+）
permits|Java 密封类型允许列表（Java 17+）
non-sealed|Java 解除密封继承限制（Java 17+）
true|Java 布尔真字面量
false|Java 布尔假字面量
null|Java 空引用字面量
object|Java 对象概念
exception|Java 异常统称
throwable|Java 可抛出对象基类
error|Java 严重错误基类
runtimeexception|Java 运行时异常基类
nullpointerexception|Java 空指针异常
indexoutofboundsexception|Java 下标越界异常
arrayindexoutofboundsexception|Java 数组下标越界异常
stringindexoutofboundsexception|Java 字符串下标越界异常
classcastexception|Java 类型转换异常
numberformatexception|Java 数字格式异常
arithmeticexception|Java 算术异常
illegalargumentexception|Java 非法参数异常
illegalstateexception|Java 非法状态异常
unsupportedoperationexception|Java 不支持操作异常
concurrentmodificationexception|Java 并发修改异常
classnotfoundexception|Java 类未找到受检异常
nosuchmethodexception|Java 方法不存在异常
nosuchfieldexception|Java 字段不存在异常
ioexception|Java IO 受检异常
filenotfoundexception|Java 文件未找到异常
sqlsyntaxerrorexception|Java SQL 语法异常
sqlexception|Java JDBC 异常基类
interruptedexception|Java 线程中断受检异常
outofmemoryerror|Java 堆内存不足错误
stackoverflowerror|Java 栈溢出错误
linkageerror|Java 类链接错误
assertionerror|Java 断言错误
threaddeath|Java 线程终止异常
string|Java 字符串类型
stringbuilder|Java 可变字符串构建器
stringbuffer|Java 同步可变字符串构建器
array|Java 数组类型
list|Java 列表接口
set|Java 集合接口
map|Java 映射接口
queue|Java 队列接口
deque|Java 双端队列接口
iterator|Java 迭代器接口
iterable|Java 可迭代接口
optional|Java 可选值容器
stream|Java 流式处理接口
lambda|Java Lambda 表达式
method|Java 方法
constructor|Java 构造器
field|Java 字段
property|Java 属性概念
package|Java 包
module|Java 模块
annotation|Java 注解
reflection|Java 反射
thread|Java 线程
runnable|Java 可运行任务接口
callable|Java 可返回结果任务接口
future|Java 异步结果接口
synchronized|Java 同步关键字
lock|Java 锁概念
mutex|Java 互斥锁概念
semaphore|Java 信号量
executor|Java 执行器接口

# Java 标准库 API
java.lang.String|Java 标准字符串类
java.lang.Object|Java 所有类的根对象
java.lang.Math|Java 数学工具类
java.lang.System|Java 系统工具类
java.lang.Thread|Java 线程类
java.lang.Exception|Java 受检异常基类
java.lang.RuntimeException|Java 运行时异常类
java.lang.StringBuilder|Java 字符串构建类
java.util.ArrayList|Java 动态数组列表
java.util.LinkedList|Java 链表实现
java.util.HashMap|Java 哈希映射实现
java.util.LinkedHashMap|Java 保持插入顺序映射
java.util.TreeMap|Java 有序映射实现
java.util.HashSet|Java 哈希集合实现
java.util.LinkedHashSet|Java 保持插入顺序集合
java.util.TreeSet|Java 有序集合实现
java.util.ArrayDeque|Java 双端队列实现
java.util.PriorityQueue|Java 优先队列实现
java.util.Iterator|Java 迭代器接口
java.util.Collections|Java 集合工具类
java.util.Arrays|Java 数组工具类
java.util.Objects|Java 对象工具类
java.util.Optional|Java 可选值容器
java.util.concurrent|Java 并发包
java.util.concurrent.Future|Java 异步结果接口
java.util.concurrent.ExecutorService|Java 执行服务接口
java.time|Java 日期时间包（Java 8+）
java.time.LocalDate|Java 本地日期类
java.time.LocalTime|Java 本地时间类
java.time.LocalDateTime|Java 本地日期时间类
java.time.Instant|Java 时间线瞬时点类
java.time.Duration|Java 时间间隔类
java.time.Period|Java 日期周期类
java.time.format.DateTimeFormatter|Java 日期格式化类
java.io.File|Java 文件路径兼容类
java.io.InputStream|Java 输入字节流
java.io.OutputStream|Java 输出字节流
java.io.BufferedReader|Java 缓冲字符读取器
java.io.BufferedWriter|Java 缓冲字符写入器
java.nio.file.Path|Java NIO 路径接口
java.nio.file.Paths|Java NIO 路径工具类
java.nio.file.Files|Java NIO 文件工具类
java.net.URL|Java URL 类
java.net.URI|Java URI 类
java.sql.Connection|JDBC 数据库连接
java.sql.PreparedStatement|JDBC 预编译语句
java.sql.ResultSet|JDBC 查询结果集
java.sql.DriverManager|JDBC 驱动管理器
java.util.regex.Pattern|Java 正则模式
java.util.regex.Matcher|Java 正则匹配器
System.out.println|Java 标准输出并换行
System.out.print|Java 标准输出不换行
public static void main|Java 程序入口方法签名
@Override|Java 覆写方法注解
@Deprecated|Java 弃用注解
@SuppressWarnings|Java 抑制编译器警告注解
@FunctionalInterface|Java 函数式接口注解
""")

SQL_TERMS = _table(r"""
select|SQL 查询数据关键字
from|SQL 指定数据源关键字
where|SQL 行过滤条件关键字
group|SQL 分组关键字
by|SQL 排序或分组依据关键字
having|SQL 分组后过滤关键字
order|SQL 排序关键字
asc|SQL 升序排序关键字
desc|SQL 降序排序关键字
distinct|SQL 消除重复行关键字
all|SQL 保留全部结果关键字
as|SQL 别名关键字
and|SQL 逻辑与关键字
or|SQL 逻辑或关键字
not|SQL 逻辑非关键字
in|SQL 集合成员测试关键字
between|SQL 范围测试关键字
like|SQL 模式匹配关键字
is|SQL 空值比较关键字
null|SQL 空值标记
exists|SQL 子查询存在性测试
case|SQL 条件表达式关键字
when|SQL CASE 条件关键字
then|SQL CASE 结果关键字
else|SQL CASE 否则结果关键字
end|SQL CASE 结束关键字
join|SQL 表连接关键字
inner|SQL 内连接类型
left|SQL 左连接方向
right|SQL 右连接方向
full|SQL 全连接方向（并非所有方言支持）
cross|SQL 笛卡尔连接类型
outer|SQL 外连接修饰词
on|SQL 连接条件关键字
using|SQL 同名列连接关键字
union|SQL 合并查询结果关键字
intersect|SQL 交集查询关键字（方言支持情况不同）
except|SQL 差集查询关键字（方言支持情况不同）
with|SQL 公用表表达式关键字
recursive|SQL 递归 CTE 修饰词
limit|SQL 结果行数限制（MySQL/PostgreSQL 等）
offset|SQL 结果偏移（方言相关）
fetch|SQL 提取行关键字
first|SQL 首行修饰词
only|SQL 仅返回关键字
insert|SQL 插入数据关键字
into|SQL 指定写入表关键字
values|SQL 插入值关键字
update|SQL 更新数据关键字
set|SQL 设置列值关键字
delete|SQL 删除数据关键字
merge|SQL 合并写入关键字（方言相关）
returning|SQL 返回写入行（方言相关）
create|SQL 创建对象关键字
alter|SQL 修改对象结构关键字
drop|SQL 删除对象关键字
truncate|SQL 清空表数据关键字
rename|SQL 重命名对象关键字
comment|SQL 注释对象关键字（方言相关）
table|SQL 表对象关键字
view|SQL 视图对象关键字
index|SQL 索引对象关键字
schema|SQL 模式对象关键字
database|SQL 数据库对象关键字
column|SQL 列对象关键字
constraint|SQL 约束对象关键字
primary|SQL 主键约束修饰词
key|SQL 键关键字
foreign|SQL 外键约束修饰词
references|SQL 外键引用关键字
unique|SQL 唯一约束关键字
check|SQL 检查约束关键字
default|SQL 默认值约束关键字
identity|SQL 标识列概念（方言相关）
sequence|SQL 序列对象（方言相关）
transaction|SQL 事务概念
begin|SQL 开始事务（方言相关）
start|SQL 开始事务关键字
commit|SQL 提交事务关键字
rollback|SQL 回滚事务关键字
savepoint|SQL 保存点关键字
release|SQL 释放保存点关键字
grant|SQL 授予权限关键字
revoke|SQL 撤销权限关键字
cascade|SQL 级联处理修饰词
restrict|SQL 限制级联修饰词
analyze|SQL 统计信息分析（方言相关）
vacuum|SQL 空间回收（PostgreSQL/SQLite 等）
explain|SQL 查询计划查看关键字
pragma|SQLite 等方言指令关键字
call|SQL 调用过程关键字（方言相关）
procedure|SQL 存储过程对象
function|SQL 函数对象
trigger|SQL 触发器对象
view|SQL 视图对象
cursor|SQL 游标对象

# 常见数据类型与函数
integer|SQL 整数类型（具体范围随方言）
int|SQL 整数类型别名（方言相关）
bigint|SQL 大整数类型
smallint|SQL 小整数类型
decimal|SQL 精确小数类型
numeric|SQL 精确数值类型
float|SQL 浮点类型
real|SQL 实数类型
 double|SQL 双精度类型（方言相关）
char|SQL 定长字符串类型
varchar|SQL 变长字符串类型
nvarchar|SQL Unicode 变长字符串（方言相关）
text|SQL 长文本类型
blob|SQL 二进制大对象类型
date|SQL 日期类型
time|SQL 时间类型
timestamp|SQL 时间戳类型
boolean|SQL 布尔类型（方言相关）
json|SQL JSON 类型或函数（方言相关）
count|SQL 计数聚合函数
sum|SQL 求和聚合函数
avg|SQL 平均值聚合函数
min|SQL 最小值聚合函数
max|SQL 最大值聚合函数
coalesce|SQL 返回首个非空值函数
nullif|SQL 相等时返回空值函数
cast|SQL 显式类型转换函数
convert|SQL 类型转换函数（方言相关）
substring|SQL 截取字符串函数（方言相关）
concat|SQL 连接字符串函数（方言相关）
length|SQL 字符串长度函数（方言相关）
upper|SQL 转大写函数
lower|SQL 转小写函数
trim|SQL 去除空白函数
round|SQL 数值四舍五入函数
abs|SQL 绝对值函数
current_date|SQL 当前日期值
current_time|SQL 当前时间值
current_timestamp|SQL 当前时间戳值

# 常用完整 SQL 片段
select distinct|SQL 查询并去重，语法受方言细节影响
group by|SQL 按列分组
order by|SQL 按表达式排序
left join|SQL 左外连接
right join|SQL 右外连接
inner join|SQL 内连接
full outer join|SQL 全外连接（并非所有方言支持）
cross join|SQL 笛卡尔连接
where exists|SQL 用存在性子查询过滤
insert into|SQL 插入目标表
insert into ... values|SQL 插入值语句模式
update ... set|SQL 更新列值语句模式
delete from|SQL 删除目标表行
create table|SQL 创建表
alter table|SQL 修改表结构
drop table|SQL 删除表
create index|SQL 创建索引
drop index|SQL 删除索引
primary key|SQL 主键约束
foreign key|SQL 外键约束
not null|SQL 非空约束
unique constraint|SQL 唯一约束
check constraint|SQL 检查约束
on delete cascade|SQL 删除时级联（方言支持不同）
with recursive|SQL 递归公用表表达式
union all|SQL 合并且保留重复行
case when|SQL 条件表达式开头
is null|SQL 空值判断
is not null|SQL 非空判断
like escape|SQL 带转义字符的模式匹配
select count|SQL 计数查询常见写法
select into|SQL 查询写入表（方言含义不同）
explain analyze|SQL 执行计划及实际分析（方言相关）
commit transaction|SQL 提交事务
rollback transaction|SQL 回滚事务
""")

JAVASCRIPT_TERMS = _table(r"""
await|JavaScript 异步等待关键字
break|JavaScript 跳出循环关键字
case|JavaScript switch 分支关键字
catch|JavaScript 异常捕获关键字
class|JavaScript 类定义关键字
const|JavaScript 块级常量声明
continue|JavaScript 继续循环关键字
debugger|JavaScript 调试器断点语句
default|JavaScript 默认导出或分支
 delete|JavaScript 删除属性运算符
do|JavaScript do-while 循环
else|JavaScript 否则分支
export|JavaScript 模块导出关键字
extends|JavaScript 类继承关键字
finally|JavaScript 异常清理块
for|JavaScript for 循环
from|JavaScript 导入来源关键字
function|JavaScript 函数定义关键字
if|JavaScript 条件关键字
import|JavaScript 模块导入关键字
in|JavaScript 属性枚举运算符
instanceof|JavaScript 原型类型检查运算符
let|JavaScript 块级变量声明
new|JavaScript 实例创建运算符
null|JavaScript 空值
of|JavaScript for-of 迭代关键字
return|JavaScript 函数返回关键字
static|JavaScript 类静态成员修饰符
super|JavaScript 父类调用关键字
switch|JavaScript 多分支选择
this|JavaScript 当前执行上下文引用
throw|JavaScript 抛出异常关键字
try|JavaScript 异常处理起始关键字
typeof|JavaScript 类型查询运算符
var|JavaScript 函数作用域变量声明
void|JavaScript 丢弃表达式值运算符
while|JavaScript while 循环
yield|JavaScript 生成器产出关键字
true|JavaScript 真布尔值
false|JavaScript 假布尔值
undefined|JavaScript 未定义值
NaN|JavaScript 非数字值
Infinity|JavaScript 无穷值
async|JavaScript 异步函数修饰词
of|JavaScript 迭代值关键字
arguments|JavaScript 函数参数对象
Array|JavaScript 数组构造器
Boolean|JavaScript 布尔构造器
Date|JavaScript 日期构造器
Error|JavaScript 错误构造器
EvalError|JavaScript 求值错误构造器
Function|JavaScript 函数构造器
Map|JavaScript 键值映射构造器
Number|JavaScript 数值构造器
Object|JavaScript 对象构造器
Promise|JavaScript 承诺构造器
Proxy|JavaScript 代理构造器
RangeError|JavaScript 范围错误构造器
ReferenceError|JavaScript 引用错误构造器
RegExp|JavaScript 正则构造器
Set|JavaScript 集合构造器
String|JavaScript 字符串构造器
Symbol|JavaScript 符号构造器
SyntaxError|JavaScript 语法错误构造器
TypeError|JavaScript 类型错误构造器
URIError|JavaScript URI 错误构造器
WeakMap|JavaScript 弱映射构造器
WeakSet|JavaScript 弱集合构造器
JSON|JavaScript JSON 全局对象
Math|JavaScript 数学全局对象
Reflect|JavaScript 反射全局对象
Intl|JavaScript 国际化全局对象
console|JavaScript 控制台全局对象
window|浏览器窗口全局对象
document|浏览器文档对象
navigator|浏览器环境信息对象
location|浏览器地址对象
localStorage|浏览器本地存储对象
sessionStorage|浏览器会话存储对象
fetch|JavaScript 网络请求函数
parseInt|JavaScript 解析整数函数
parseFloat|JavaScript 解析浮点数函数
isNaN|JavaScript 非数字检查函数
isFinite|JavaScript 有限数检查函数
encodeURI|JavaScript URI 编码函数
decodeURI|JavaScript URI 解码函数
encodeURIComponent|JavaScript 组件编码函数
decodeURIComponent|JavaScript 组件解码函数
setTimeout|JavaScript 延迟定时器函数
setInterval|JavaScript 周期定时器函数
clearTimeout|JavaScript 清除延迟定时器
clearInterval|JavaScript 清除周期定时器
queueMicrotask|JavaScript 排队微任务函数
structuredClone|JavaScript 结构化复制函数
Array.isArray|JavaScript 数组类型检查
Array.from|JavaScript 创建数组
Array.of|JavaScript 从参数创建数组
Array.prototype.map|JavaScript 数组映射方法
Array.prototype.filter|JavaScript 数组过滤方法
Array.prototype.reduce|JavaScript 数组归约方法
Array.prototype.forEach|JavaScript 数组遍历方法
Array.prototype.find|JavaScript 数组查找方法
Array.prototype.findIndex|JavaScript 查找下标方法
Array.prototype.includes|JavaScript 数组包含检查
Array.prototype.indexOf|JavaScript 数组下标查询
Array.prototype.join|JavaScript 数组连接字符串
Array.prototype.slice|JavaScript 数组浅拷贝切片
Array.prototype.splice|JavaScript 数组增删方法
Array.prototype.push|JavaScript 数组尾部追加
Array.prototype.pop|JavaScript 数组尾部移除
Array.prototype.shift|JavaScript 数组头部移除
Array.prototype.unshift|JavaScript 数组头部追加
Array.prototype.sort|JavaScript 数组排序方法
Array.prototype.reverse|JavaScript 数组反转方法
Object.keys|JavaScript 对象键列表
Object.values|JavaScript 对象值列表
Object.entries|JavaScript 对象键值列表
Object.assign|JavaScript 对象属性合并
Object.create|JavaScript 指定原型创建对象
Object.freeze|JavaScript 冻结对象
Object.hasOwn|JavaScript 自有属性检查
JSON.parse|JavaScript JSON 字符串解析
JSON.stringify|JavaScript JSON 序列化
Math.max|JavaScript 最大值函数
Math.min|JavaScript 最小值函数
Math.round|JavaScript 四舍五入函数
Math.floor|JavaScript 向下取整函数
Math.ceil|JavaScript 向上取整函数
Math.random|JavaScript 伪随机数函数
Promise.all|JavaScript 等待全部承诺
Promise.allSettled|JavaScript 等待全部 settled
Promise.any|JavaScript 任一成功承诺
Promise.race|JavaScript 竞争首个承诺
Promise.resolve|JavaScript 创建已解决承诺
Promise.reject|JavaScript 创建已拒绝承诺
console.log|JavaScript 控制台普通日志
console.error|JavaScript 控制台错误日志
console.warn|JavaScript 控制台警告日志
console.table|JavaScript 控制台表格输出
document.querySelector|浏览器按 CSS 选择器取首元素
document.querySelectorAll|浏览器按 CSS 选择器取元素集合
document.getElementById|浏览器按 ID 取元素
document.createElement|浏览器创建 DOM 元素
Element.addEventListener|浏览器注册 DOM 事件监听
Event.preventDefault|浏览器阻止默认事件
window.addEventListener|浏览器注册窗口事件
window.requestAnimationFrame|浏览器请求下一帧回调
fetch().then|JavaScript 网络承诺链式成功回调
fetch().catch|JavaScript 网络承诺链式错误回调
async function|JavaScript 异步函数声明语法
arrow function|JavaScript 箭头函数语法
optional chaining|JavaScript 可选链语法
nullish coalescing|JavaScript 空值合并语法
object destructuring|JavaScript 对象解构语法
array destructuring|JavaScript 数组解构语法
template literal|JavaScript 模板字符串
spread syntax|JavaScript 展开语法
rest parameter|JavaScript 剩余参数语法
for of|JavaScript 值迭代循环
for in|JavaScript 属性迭代循环
try catch|JavaScript 异常捕获结构
export default|JavaScript 默认导出语法
export named|JavaScript 命名导出概念
import default|JavaScript 默认导入语法
import named|JavaScript 命名导入语法
""")

COMMON_TERMS = _table(r"""
api|应用程序编程接口
argument|函数调用实参
parameter|函数定义形参
return|返回值或返回语句
value|程序中的值
variable|变量
constant|常量
literal|字面量
expression|表达式
statement|语句
operator|运算符
operand|运算数
keyword|关键字
identifier|标识符
function|函数
method|方法
class|类
type|类型
instance|实例
object|对象
module|模块
package|包
namespace|命名空间
scope|作用域
closure|闭包
callback|回调函数
iterator|迭代器
generator|生成器
coroutine|协程
async|异步
await|等待异步结果
sync|同步
thread|线程
process|进程
parallel|并行
concurrency|并发
lock|锁
mutex|互斥锁
queue|队列
stack|栈
heap|堆
pointer|指针概念
reference|引用
address|地址
memory|内存
buffer|缓冲区
cache|缓存
stream|流
input|输入
output|输出
stdin|标准输入
stdout|标准输出
stderr|标准错误输出
file|文件
path|路径
folder|文件夹
directory|目录
extension|扩展名
encoding|编码
utf-8|UTF-8 编码
unicode|Unicode 字符集
ascii|ASCII 字符集
binary|二进制
byte|字节
bit|位
string|字符串
character|字符
integer|整数
float|浮点数
number|数值
boolean|布尔值
array|数组
list|列表
set|集合
map|映射
hash|哈希
key|键
null|空值
none|空对象值
undefined|未定义值
exception|异常
error|错误
warning|警告
traceback|错误回溯
stacktrace|调用栈回溯
assertion|断言
bug|程序缺陷
fix|修复
retry|重试
retries|重试次数
attempt|尝试次数
timeout|超时
latency|延迟
throughput|吞吐量
request|请求
response|响应
header|请求或响应头
body|请求或响应正文
status|状态
statuscode|状态码
payload|载荷数据
protocol|协议
socket|套接字
port|端口
host|主机
server|服务器
client|客户端
localhost|本机主机名
url|统一资源定位符
uri|统一资源标识符
query|查询
transaction|事务
schema|模式
record|记录
row|行
column|列
field|字段
index|索引
primarykey|主键概念
foreignkey|外键概念
constraint|约束
migration|数据库迁移
syntax|语法
runtime|运行时
compile|编译
compiler|编译器
interpreter|解释器
runtimeerror|运行时错误
version|版本
release|发布版本
legacy|遗留代码
deprecated|已弃用
stable|稳定
experimental|实验性
configuration|配置
config|配置
option|选项
flag|标志参数
verbose|详细输出
debug|调试
logging|日志记录
log|日志
level|级别
warninglevel|警告级别
test|测试
unit test|单元测试
integration test|集成测试
regression test|回归测试
assert equal|断言相等
mock|模拟对象
fixture|测试夹具
coverage|覆盖率
dependency|依赖
library|库
framework|框架
repository|代码仓库
commit|提交
branch|分支
merge|合并
conflict|冲突
pull request|合并请求
build|构建
compile time|编译时
runtime environment|运行环境
pointer arithmetic|指针算术概念
by id|按 ID 匹配
by name|按名称匹配
case sensitive|区分大小写
case insensitive|不区分大小写
read only|只读
write only|只写
read write|可读写
immutable|不可变
mutable|可变
thread safe|线程安全
idempotent|幂等
atomic|原子性
synchronous|同步的
asynchronous|异步的
serializable|可序列化
reflection|反射
annotation|注解
metadata|元数据
schema migration|模式迁移
connection pool|连接池
retry policy|重试策略
backoff|退避等待
exponential backoff|指数退避
page size|分页大小
offset|偏移量
limit|上限
count|计数
sort key|排序键
filter predicate|过滤谓词
join condition|连接条件
primary key constraint|主键约束
foreign key constraint|外键约束
""")

LEGACY_TERMS = {
    "import": "导入", "export": "导出", "class": "类", "function": "函数",
    "method": "方法", "module": "模块", "package": "包", "library": "库",
    "interface": "接口", "argument": "参数", "parameter": "参数",
    "return": "返回", "callback": "回调", "handler": "处理器",
    "request": "请求", "response": "响应", "server": "服务端",
    "client": "客户端", "cache": "缓存", "queue": "队列", "stack": "栈",
    "buffer": "缓冲区", "thread": "线程", "process": "进程",
    "state": "状态", "graph": "图", "node": "节点", "edge": "边",
    "upload": "上传", "download": "下载", "file": "文件", "path": "路径",
    "directory": "目录", "config": "配置", "setting": "设置",
    "option": "选项", "value": "值", "key": "键", "list": "列表",
    "array": "数组", "dict": "字典", "map": "映射", "set": "集合",
    "item": "项", "element": "元素", "index": "索引", "count": "数量",
    "total": "总数", "number": "数字", "size": "大小", "length": "长度",
    "current": "当前", "previous": "上一个", "next": "下一个",
    "max": "最大", "min": "最小", "user": "用户", "name": "名称",
    "data": "数据", "model": "模型", "view": "视图", "page": "页面",
    "form": "表单", "field": "字段", "record": "记录", "table": "表",
    "query": "查询", "result": "结果", "error": "错误", "message": "消息",
    "event": "事件", "listener": "监听器", "token": "令牌",
    "session": "会话", "auth": "认证", "login": "登录", "logout": "登出",
    "create": "创建", "delete": "删除", "update": "更新", "read": "读取",
    "write": "写入", "load": "加载", "save": "保存", "parse": "解析",
    "render": "渲染", "build": "构建", "init": "初始化",
    "validate": "校验", "serialize": "序列化", "encode": "编码",
    "decode": "解码", "encrypt": "加密", "decrypt": "解密",
    "test": "测试", "mock": "模拟", "debug": "调试", "log": "日志",
    "logger": "日志器", "level": "级别", "timeout": "超时",
    "retry": "重试", "limit": "限制", "range": "范围", "offset": "偏移",
    "header": "请求头", "body": "请求体", "status": "状态",
    "code": "代码", "type": "类型", "format": "格式", "version": "版本",
    "default": "默认", "custom": "自定义", "global": "全局",
    "local": "本地", "remote": "远程", "temp": "临时", "tmp": "临时",
    "src": "源", "dest": "目标", "target": "目标", "source": "源",
    "parent": "父级", "child": "子级", "root": "根",
    "async": "异步", "await": "等待异步结果", "yield": "产出生成器值",
    "const": "常量", "let": "块级变量", "var": "变量", "def": "定义函数",
    "if": "条件判断", "else": "否则", "elif": "否则如果",
    "while": "条件循环", "for": "循环", "break": "跳出循环",
    "continue": "继续下一轮循环", "try": "尝试执行", "catch": "捕获异常",
    "except": "捕获异常", "finally": "最终执行", "raise": "抛出异常",
    "throw": "抛出异常", "null": "空值", "none": "空值",
    "true": "真", "false": "假", "bool": "布尔类型", "boolean": "布尔类型",
    "int": "整数", "integer": "整数", "float": "浮点数", "double": "双精度浮点数",
    "str": "字符串", "string": "字符串", "char": "字符", "byte": "字节",
    "bytes": "字节序列", "void": "无返回值", "object": "对象",
    "public": "公开访问", "private": "私有访问", "protected": "受保护访问",
    "static": "静态", "abstract": "抽象", "extends": "继承",
    "implements": "实现接口", "super": "父类", "self": "当前实例",
    "constructor": "构造函数", "destructor": "析构函数", "instance": "实例",
    "inheritance": "继承", "polymorphism": "多态", "encapsulation": "封装",
    "decorator": "装饰器", "generator": "生成器", "iterator": "迭代器",
    "iterable": "可迭代对象", "lambda": "匿名函数", "closure": "闭包",
    "recursion": "递归", "exception": "异常", "assert": "断言",
    "middleware": "中间件", "router": "路由器", "route": "路由",
    "endpoint": "接口端点", "database": "数据库", "transaction": "事务",
    "schema": "结构定义", "migration": "迁移", "repository": "仓库",
    "commit": "提交", "branch": "分支", "merge": "合并", "rebase": "变基",
    "push": "推送", "pull": "拉取", "fetch": "获取", "clone": "克隆",
    "dependency": "依赖", "dependencies": "依赖项", "compiler": "编译器",
    "runtime": "运行时", "framework": "框架", "component": "组件",
    "promise": "异步结果对象", "future": "未来结果对象", "coroutine": "协程",
    "mutex": "互斥锁", "lock": "锁", "deadlock": "死锁", "atomic": "原子操作",
    "socket": "套接字", "port": "端口", "host": "主机", "connection": "连接",
    "protocol": "协议", "http": "超文本传输协议", "https": "安全超文本传输协议",
    "tcp": "传输控制协议", "udp": "用户数据报协议", "dns": "域名系统",
    "api": "应用程序接口", "sdk": "软件开发工具包", "cli": "命令行界面",
    "gui": "图形用户界面", "json": "JSON 数据格式", "xml": "XML 标记格式",
    "html": "超文本标记语言", "css": "层叠样式表", "sql": "结构化查询语言",
    "id": "标识", "get": "获取", "by": "根据", "is": "是否", "has": "是否具有",
    "enabled": "已启用", "disabled": "已禁用", "valid": "有效", "invalid": "无效",
    "username": "用户名", "password": "密码", "email": "电子邮箱",
    "permission": "权限", "access": "访问", "memory": "内存", "allocation": "分配",
}

LEGACY_PHRASES = {
    "connection refused": "连接被拒绝：目标地址未接受连接。",
    "connection timed out": "连接超时：未在规定时间内建立连接。",
    "permission denied": "权限被拒绝：当前身份没有执行该操作的权限。",
    "access denied": "访问被拒绝：当前身份缺少访问权限。",
    "file not found": "文件未找到：指定路径不存在或无法访问。",
    "module not found": "模块未找到：检查依赖是否安装以及导入路径。",
    "no such file or directory": "没有该文件或目录：检查路径和文件名。",
    "out of memory": "内存不足：可用内存不足以完成操作。",
    "stack overflow": "栈溢出：调用栈空间耗尽，常见于过深递归。",
    "null pointer exception": "空指针异常：操作了空对象引用。",
    "index out of range": "索引越界：索引超出集合允许的范围。",
    "division by zero": "除零错误：除数为零。",
    "syntax error": "语法错误：代码不符合语言的语法规则。",
    "type error": "类型错误：数据类型不符合当前操作要求。",
    "invalid argument": "无效参数：参数值或格式不符合要求。",
    "not implemented": "尚未实现：对应功能没有实现。",
    "too many requests": "请求过多：服务正在限流。",
    "bad request": "错误请求：请求格式或参数不被服务接受。",
    "internal server error": "服务器内部错误：服务端处理请求时发生异常。",
    "read only": "只读：允许读取，不允许修改。",
    "event loop": "事件循环：持续调度事件和异步任务的运行机制。",
    "garbage collection": "垃圾回收：自动回收不再使用的内存。",
    "race condition": "竞态条件：结果受到并发执行顺序影响。",
    "dependency injection": "依赖注入：由外部提供组件所依赖的对象。",
    "unit test": "单元测试：验证独立函数或组件的行为。",
    "pull request": "合并请求：请求审查并合并代码变更。",
    "user_name": "用户名", "username": "用户名", "uploadfile": "上传文件",
    "getuserbyid": "根据 ID 获取用户", "max_retry_count": "最大重试次数",
}


# The public tables are merged for consumers that only need one vocabulary.
WORDS: dict[str, str] = {}
PHRASES: dict[str, str] = {}
for _group in (PYTHON_TERMS, JAVA_TERMS, SQL_TERMS, JAVASCRIPT_TERMS, COMMON_TERMS):
    for _key, _meaning in _group.items():
        WORDS[_key] = _meaning

# Single-token entries are words; dotted APIs, operators and multiword syntax are phrases.
for _key, _meaning in WORDS.items():
    if any(ch in _key for ch in (".", " ", "(", ")", "@", "-")):
        PHRASES[_key] = _meaning

# Legacy meanings are intentionally applied last: they are the precise overrides.
WORDS.update(LEGACY_TERMS)
PHRASES.update(LEGACY_PHRASES)

# Keep WORDS single-word-only while retaining every phrase in PHRASES.
for _key in tuple(WORDS):
    if _key in PHRASES:
        del WORDS[_key]

# Re-export grouped data as immutable-by-convention public dictionaries only.
del _group, _key, _meaning
