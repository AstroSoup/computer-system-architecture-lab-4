# Лабораторная работа №4 по дисциплине "Архитектура компьютера".

Выполнил: Горин Семён Дмитриевич \
Группа: P3208 \
Вариант: `asm | acc | neum | mc | tick | binary | stream | port | pstr | prob2 | superscalar`

## Язык программирования

Язык программирования ассемблера описанный в форме РБНФ:
```
program            ::= { line }
line               ::= [ label ] [ operation ] [ comment ] "\n"

label              ::= label_name ":"

operation          ::= instruction | directive

directive          ::= section | org | data

section            ::= ".text" | ".data"
org                ::= ".org" (uint | hex)
data               ::= ((".word" (int | hex)) | (".byte" (int | hex | string)))
string             ::= '"' { <any symbol except '"'> } '"'

instruction        ::= io_command (absolute_address | indirect_address)
                     | address_command(".b" | ".w" | "") (indirect_address | absolute_address | relative_address | immediate_value)
                     | no_address_command
                     | jmp_command (absolute_address | indirect_address)
io_command         ::= "in" 
                     | "out"
address_command    ::= "ld" 
                     | "st" 
                     | "add" 
                     | "sub" 
                     | "and" 
                     | "or"
                     | "mul"
no_address_command ::= "halt" 
                     | "nop" 
                     | "clr" 
                     | "not" 
                     | "inc" 
                     | "dec"
jmp_command        ::= "jmp" 
                     | "bzs" 
                     | "bzns" 
                     | "bcs" 
                     | "bcns" 
                     | "bvs" 
                     | "bvns" 
                     | "bns" 
                     | "bnns"
indirect_address   ::= "(" (uint | hex | label_name) ")"
absolute_address   ::= "$" (uint | hex | label_name)
relative_address   ::= int | hex | label_name
immediate_value    ::= "#" (int | hex | label_name)
int                ::= [ "-" ] uint
hex                ::= "0x" <any of "0-9 a-f A-F"> { <any of "0-9 a-f A-F"> }
uint               ::= <any of "0-9"> { <any of "0-9"> }
label_name         ::= <any of "a-z A-Z _"> { <any of "a-z A-Z 0-9 _"> }
comment            ::= ";" { <any symbol except "\n"> }
```
### Семантика
Операции:
- `in` --- Считать данные с выхода внешнего устройства в аккумулятор
- `out` --- Подать данные с акумулятора на вход внешнего устройства
- `ld` --- загрузить данные из памяти в аккумулятор
- `st` --- сохранить данные аккумулятора в память
- `add` --- сложить значение в аккумуляторе с операндом
- `sub` --- вычесть из аккумулятора операнд
- `and` --- битовое И между аккумулятором и операндом
- `or` --- битовое ИЛИ между аккумулятором и операндом
- `mul` --- умножить аккумулятор на операнд
- `halt` --- остановить работу процессора
- `nop` --- нет операции
- `clr` --- поместить 0 в аккумулятор
- `not` --- битовое НЕ над аккумулятором
- `inc` --- увеличить значение в аккумуляторе на 1
- `dec` --- уменьшить значение в аккумуляторе на 1
- `jmp` --- выполнить безусловный переход по адресу
- `bzs` --- выполнить переход если z == 1
- `bzns` --- выполнить переход если z == 0
- `bcs` --- выполнить переход если c == 1
- `bcns` --- выполнить переход если c == 0
- `bvs` --- выполнить переход если v == 1
- `bvns` --- выполнить переход если v == 0
- `bns` --- выполнить переход если n == 1
- `bnns` --- выполнить переход если n == 0

- `.word` --- записать в память 32-битное значение
- `.byte` --- записать в память 8-битное значение
- `.org` --- переместить адрес начала текущей секции 
- `.text` --- указатель начала секции инструкций
- `.data` --- указатель начала секции данных

### Адресация
- относительная
- абсолютная
- косвенная
- прямая загрузка операнда
- Размер операнда(только для `ld`/`st` инструкций):
    - байт
    - слово

### Литералы
В секции данных мы можем располагать символьные и численные литералы. 

Символьные литералы преобразуются в ascii репрезентацию.

Инструкции поддерживают прямую загрузку численных литералов размером до 23 бит.
## Организация памяти

Память реализует Принстонскую модель организации памяти. Длина машинного слова -- 32 бита. Адресация ячеек в памяти байтовая, однако шина доступа к ней имеет ширину машинного слова.

### Модель памяти

Расположение в памяти инструкций и данных ложится на плечи программиста. Далее представлен пример организации данных в памяти.

```
           Registers
+------------------------------+
| AC     SHADOW_AC     DR      |
| AR     SHADOW_AR     PC      |
+------------------------------+
  Instruction and data memory
+------------------------------+
| 00   : value                 |
| 01   : value                 |
| 02   : value                 |
|     ...                      |
| n    : program start         |
| n + 1: instruction           |
|     ...                      |
| n + m: halt                  |
|     ...                      |
+------------------------------+
```

За загрузку в память бинарного файла отвечает отдельный компонент, загрузчик, устанавливающий значение PC, и распределяющий секции по памяти в соответствии с заголовком исполняемого бинарного файла.


## Система команд
Каждая команда занимает 1 машинное слово в памяти. На опкод отводится 9 бит, на операнд -- 23.


| команда | количество тактов | описание |
| ------- | ----------------- | -------- |
| nop | 4 | plain nothingness |
| halt | 4 | halt execution |
| clr | 5 | 0 -> acc |
| not | 5 | ~acc -> acc |
| inc | 5 | acc + 1 -> acc |
| dec | 5 | acc - 1 -> acc |
| ld.w_immediate | 5 | DR[22:0] -> acc |
| ld.w_relative | 7 | mem(pc + DR[22:0]) -> acc |
| ld.w_absolute | 7 | mem(DR[22:0]) -> acc |
| ld.w_indirect | 9 | mem(mem(DR[22:0])) -> acc |
| ld.b_immediate | 5 | DR[7:0] -> acc |
| ld.b_relative | 7 | mem(pc + DR)[7:0] -> acc |
| ld.b_absolute | 7 | mem(DR)[7:0] -> acc |
| ld.b_indirect | 9 | mem(mem(DR))[7:0] -> acc |
| st.w_relative | 6 | acc[22:0] -> mem(pc + DR[22:0]) |
| st.w_absolute | 6 | acc[22:0] -> mem(DR[22:0]) |
| st.w_indirect | 8 | acc[22:0] -> mem(mem(DR[22:0])) |
| st.b_relative | 6 | acc[7:0] -> mem(pc + DR[22:0]) |
| st.b_absolute | 6 | acc[7:0] -> mem(DR[22:0]) |
| st.b_indirect | 8 | acc[7:0] -> mem(mem(DR[22:0])) |
| add_immediate | 5 | DR[22:0] + acc -> acc |
| add_relative | 7 | mem(pc + DR[22:0]) + acc -> acc |
| add_absolute | 7 | mem(DR[22:0]) + acc -> acc |
| add_indirect | 9 | mem(mem(DR[22:0])) + acc -> acc |
| sub_immediate | 5 | acc - DR[22:0] -> acc |
| sub_relative | 7 | acc - mem(pc + DR[22:0]) -> acc |
| sub_absolute | 7 | acc - mem(DR[22:0]) -> acc |
| sub_indirect | 9 | acc - mem(mem(DR[22:0])) -> acc |
| and_immediate | 5 | DR[22:0] & acc -> acc |
| and_relative | 7 | mem(pc + DR[22:0]) & acc -> acc |
| and_absolute | 7 | mem(DR[22:0]) & acc -> acc |
| and_indirect | 9 | mem(mem(DR[22:0])) & acc -> acc |
| or_immediate | 5 | DR[22:0] \| acc -> acc |
| or_relative | 7 | mem(pc + DR[22:0]) \| acc -> acc |
| or_absolute | 7 | mem(DR[22:0]) \| acc -> acc |
| or_indirect | 9 | mem(mem(DR[22:0])) \| acc -> acc |
| mul_immediate | 5 | DR[22:0] * acc -> acc |
| mul_relative | 7 | mem(pc + DR[22:0]) * acc -> acc |
| mul_absolute | 7 | mem(DR[22:0]) * acc -> acc |
| mul_indirect | 9 | mem(mem(DR[22:0])) * acc -> acc |
| in_absolute | 6 | device(DR[22:0]) -> acc |
| in_indirect | 9 | device(mem(DR[22:0])) -> acc |
| out_absolute | 6 | acc -> device(DR[22:0]) |
| out_indirect | 9 | acc -> device(mem(DR[22:0])) |
| jmp_relative | 5 | pc + DR[22:0] -> pc |
| jmp_indirect | 8 | mem(DR[22:0]) -> pc |
| bzs_relative | 6 | if (z == 1) pc + DR[22:0] -> pc |
| bzs_indirect | 8 | if (z == 1) pc + mem(DR[22:0]) -> pc |
| bzns_relative | 6 | if (z == 0) pc + DR[22:0] -> pc |
| bzns_indirect | 8 | if (z == 0) pc + mem(DR[22:0]) -> pc |
| bcs_relative | 6 | if (c == 1) pc + DR[22:0] -> pc |
| bcs_indirect | 8 | if (c == 1) pc + mem(DR[22:0]) -> pc |
| bcns_relative | 6 | if (c == 0) pc + DR[22:0] -> pc |
| bcns_indirect | 8 | if (c == 0) pc + mem(DR[22:0]) -> pc |
| bvs_relative | 6 | if (v == 1) pc + DR[22:0] -> pc |
| bvs_indirect | 8 | if (v == 1) pc + mem(DR[22:0]) -> pc |
| bvns_relative | 6 | if (v == 0) pc + DR[22:0] -> pc |
| bvns_indirect | 8 | if (v == 0) pc + mem(DR[22:0]) -> pc |
| bns_relative | 6 | if (n == 1) pc + DR[22:0] -> pc |
| bns_indirect | 8 | if (n == 1) pc + mem(DR[22:0]) -> pc |
| bnns_relative | 6 | if (n == 0) pc + DR[22:0] -> pc |
| bnns_indirect | 8 | if (n == 0) pc + mem(DR[22:0]) -> pc |
| swp_relative | 5 | acc <-> shadow_acc; pc + DR[22:0] -> shadow_ar |
| swp_absolute | 5 | acc <-> shadow_acc; DR[22:0] -> shadow_ar |
| swp_indirect | 8 | acc <-> shadow_acc; mem(DR[22:0]) -> shadow_ar |
| flsh.ww_relative | 6 | acc -> mem(pc + DR[22:0]); shadow_acc -> mem(shadow_ar) |
| flsh.ww_absolute | 6 | acc -> mem(DR[22:0]); shadow_acc -> mem(shadow_ar) |
| flsh.ww_indirect | 8 | acc -> mem(mem(DR[22:0])); shadow_acc -> mem(shadow_ar) |
| flsh.bb_relative | 6 | acc -> mem(pc + DR[22:0]); shadow_acc -> mem(shadow_ar) |
| flsh.bb_absolute | 6 | acc -> mem(DR[22:0]); shadow_acc -> mem(shadow_ar) |
| flsh.bb_indirect | 8 | acc -> mem(mem(DR[22:0])); shadow_acc -> mem(shadow_ar) |
| flsh.wb_relative | 6 | acc -> mem(pc + DR[22:0]); shadow_acc -> mem(shadow_ar) |
| flsh.wb_absolute | 6 | acc -> mem(DR[22:0]); shadow_acc -> mem(shadow_ar) |
| flsh.wb_indirect | 8 | acc -> mem(mem(DR[22:0])); shadow_acc -> mem(shadow_ar) |
| flsh.bw_relative | 6 | acc -> mem(pc + DR[22:0]); shadow_acc -> mem(shadow_ar) |
| flsh.bw_absolute | 6 | acc -> mem(DR[22:0]); shadow_acc -> mem(shadow_ar) |
| flsh.bw_indirect | 8 | acc -> mem(mem(DR[22:0])); shadow_acc -> mem(shadow_ar) |

## Транслятор
CLI:
```
python translator.py <input_file> <output_file> [--debug=<debug_file>] [--optimize]
```
Код: [translator.py](./src/translator.py)


### Этапы трансляции
- Чтение исходного файла
- Удаление комментариев и преобразование в список строк программы
- Парсинг в удобное для манипулирования программное представление
- При наличии на входе транслятора флага `--optimize` происходит оптимизация инструкций с использованием операций с теневым регистром (подробнее о ней далее)
- Формирование адресного пространства и замена текстовых меток на конкретные численные значения
- Кодирование токенов в бинарный формат
- Запись инструкций в указанный файл

В бинарном файле формируется хедер следующего содержания:
| field | offset | size |
| ----- | ------ | ---- |
| magic number (600DCAFE) | 0x0 | 4 |
| entrypoint | 0x4 | 4(in reality its 23 bit value but why not give it a full word for easier parsing) |  
| sec_start | 0x8 | 4 |
| sec_size | 0xC | 4 |
| ... | ... | ... |
| end of header (BAADCAFE) | ... | 4 |

После хедера следуют секции программы (.data, .text) в том же порядке в котором они были указаны в исходном коде.

### Оптимизация
Оптимизация выполняется независимо для каждой секцией `.text`. Цель оптимизации --- заменить повторяющиеся цепочки вида `load - modify - store` на более компактную и менее часто обращающаюся к памяти последовательность с использованием `swap` и `flush` операций. 

Оптимизируемый фрагмент должен удовлетворять следующим условиям:

- блок должен начинаться с инструкции `st` с меткой в качестве операнда и прямой абсолютной или относительной адресацией.
- следующей за `st` инструкцией должна идти инструкция `ld` с меткой в качестве операнда и прямой абсолютной или относительной адресацией.
- метки-операнды `ld` и `st` должны быть различны.

В таком случае мы заменяем первую пару `ld ; st` на `swp`.

После этого анализ продолжается вперёд по потоку инструкций. Оптимизация может быть применена только в том случае, если между текущим состоянием и закрывающей записью нет инструкций, которые:

- могут изменить ход выполнения в зависимости от рантайма;
- могут быть целью прыжка;
- нарушают безопасность преобразования.

Если закрывающая инструкция `st` для текущей метки найдена, рассматриваются два случая:
- Сразу после закрывающего `st`, следует `ld` из метки, на данный момент находящейся в свапе. \
Это образует пинг-понг паттерн,и в таком случае мы выполняем очередной обмен через `swp`, и продолжаем поиск закрывающего `st`.
- Сразу после закрывающего `st`, следует любая другая инструкция. \
В таком случае выполняется сохранение состояния через `flsh`, то есть активный свап заканчивается записью в память.

Если на некотором этапе закрывающая запись не была найдена, однако ранее был замечен пинг-понг паттерн, то последняя запись паттерна заменяется на сохранение состояния свапа при помощи `flsh`. Таким образом, транслятор не теряет уже найденную оптимизацию и корректно завершает обработку доступного префикса цепочки.

Пример оптимизации:

Код, не оптимизированный транслятором:
```
<address> | <hex_code> | <mnemonic>                
8         | 0x03fffff4 | ld.w: mem(pc + -12) -> acc
12        | 0x02000000 | inc: acc + 1 -> acc       
16        | 0x07ffffec | st.w: acc -> mem(pc + -20)
20        | 0x03ffffec | ld.w: mem(pc + -20) -> acc
24        | 0x02000000 | inc: acc + 1 -> acc       
28        | 0x07ffffe4 | st.w: acc -> mem(pc + -28)
32        | 0x03ffffdc | ld.w: mem(pc + -36) -> acc
36        | 0x02000000 | inc: acc + 1 -> acc       
40        | 0x07ffffd4 | st.w: acc -> mem(pc + -44)
44        | 0x03ffffd4 | ld.w: mem(pc + -44) -> acc
48        | 0x13800000 | out: acc -> device(0)     
52        | 0x03ffffc8 | ld.w: mem(pc + -56) -> acc
56        | 0x13800000 | out: acc -> device(0)     
60        | 0x00800000 | halt: halt execution      
```
Полученное время исполнения(доступ к памяти осуществляется за 1 такт):
```
Program executed after 0084 ticks.
```
Код оптимизированный транслятором:
```
<address> | <hex_code> | <mnemonic>                                                 
8         | 0x03fffff4 | ld.w: mem(pc + -12) -> acc                                 
12        | 0x02000000 | inc: acc + 1 -> acc                                        
16        | 0x1fffffec | swp: acc <-> shadow_acc; pc + -20 -> shadow_ar             
20        | 0x03ffffec | ld.w: mem(pc + -20) -> acc                                 
24        | 0x02000000 | inc: acc + 1 -> acc                                        
28        | 0x1fffffe4 | swp: acc <-> shadow_acc; pc + -28 -> shadow_ar             
32        | 0x02000000 | inc: acc + 1 -> acc                                        
36        | 0x217fffd8 | flsh.ww: acc -> mem(pc + -40); shadow_acc -> mem(shadow_ar)
40        | 0x03ffffd8 | ld.w: mem(pc + -40) -> acc                                 
44        | 0x13800000 | out: acc -> device(0)                                      
48        | 0x03ffffcc | ld.w: mem(pc + -52) -> acc                                 
52        | 0x13800000 | out: acc -> device(0)                                      
56        | 0x00800000 | halt: halt execution                                      

```
Полученное время исполнения (доступ к памяти осуществляется за 1 такт)
```
Program executed after 0076 ticks.
```

## Модель процессора
CLI:
```
python machine.py <input_file> --conf=<config_file> 
```
Журнал состояний выводится в консоль, можно перенаправить в файл при помощи `2>`.

Код: [machine.py](./src/machine.py)

Конфигурация модели задается через `.yaml` файл следующего содержания:

```yaml
# execution limits
memory_size: 128
limit: 4096
# list of devices seen by the model. 
# Addresses assigned based on position in this list.
devices:
  - in: []
    out: []
# What to output in execution logs.
report:
  # executes before starting the model
  - type: "first"
    view: |
      tick | mnemonic
      -------------------------------------------------
  # executes on each step of the model
  - type: "step-by-step"
    view: |
      {tick} | {mnemonic}
  # executes after the model stopped running
  - type: "last"
    view: |
      -------------------------------------------------
      Program executed after {tick} ticks. Final state:
      in: 
      {in(0):sym}
      out: 
      {out(0):dec}
      memory_dump:
      {memory(0:128:16)}
```
Для вывода доступны состояния любого из регистров или микрорегистров(`{acc}`, `{shadow_acc}`, `{ar}`, `{shadow_ar}`, `{pc}`, `{dr}`, `{mir}`, `{mpc}`, `{N}`, `{Z}`, `{V}`, `{C}`), мнемоники микрокоманд (`{mnemonics}`), текущий такт (`{tick}`), буферы ввода и вывода устройства с адресом n (`{in(n)}`, `{out(n)}`), состояние блока памяти начиная с ячейки start, заканчивая ячейкой end, выводя по step ячеек в строку (`{memory(start:end:step)}`).

### Datapath

Процессор построен на базе аккумуляторной архитектуры с применением паттерна теневого регистра для уменьшения обращений к памяти и параллелезации записей в память. 

![Datapath scheme](assets/datapath/scheme.svg)

#### Сигналы

- `read_word` --- считать из памяти слово начинающееся по адресу в AR
- `read_byte` --- считать из памяти байт по адресу в AR
- `store_word` --- записать в память слово в ячейки начинающиеся по адресу в AR
- `store_byte` --- записать в память байт по адресу в AR
- `latch_ar` --- защелкнуть AR
- `latch_shadow_ar` --- защелкнуть SHADOW_AR
- `latch_dr` --- защелкнуть DR
- `latch_pc` --- защелкнуть PC
- `latch_acc` --- защелкнуть AC
- `latch_shadow` --- защелкнуть SHADOW_ACC
- `latch_input_address` ---  защелкнуть адрес входного устройства
- `latch_output_address` --- защелкнуть адрес выходного устройства
- `read_input` --- получить данные с устройства по выбранному адресу
- `write_output` --- записать данные на устройство по выбранному адресу
- `sh_ar_or_addr` --- подать на вход AR SHADOW AR или выход data_or_inst
- `data_or_inst` --- подать на левый вход sh_ar_or_addr адрес следующей инструкции или адрес данных в памяти
- `rel_or_abs` --- подать на левый вход data_or_inst относительный или абсолютный адрес
- `next_or_offset` --- подать на левый вход сумматора +4 или сдвиг для относительной адресации
- `ext_data` --- расширить знак DR[22:0]
- `in_or_mem` --- подать на правый вход АЛУ данные из DR или из входного устройства
- `ext_acc` --- расширить знак AC[8:0]
- `sa_or_alu` --- подать на вход AC SHADOW_AC или результат АЛУ
- `add` --- выполнить сложение в сумматоре
- `operation` --- численное обозначение комбинационной схемы которую должно активировать АЛУ
- `st_sh` --- воспользоваться теневыми версиями регистров для записи в память

### Control Unit

Управляющеее устройство построено на базе микроинструкций. Коды операций совмещенные с режимами адресации (для упрощения внутренного устройства control unit'а) получаются из справочной таблицы.

![Control Unit scheme](assets/control_unit/scheme.svg)

#### Сигналы
- `type` --- указывает на тип микрокоманды
- `jmp` --- обозначает микрокоманду перехода (условного или безусловного)
- `cmp` --- условный переход
- `sel_cmp` --- трехбитовый сигнал для выбора признака сравнения
- `dispatch` --- чтение и декодирование адреса начала инструкции в памяти микрокоманд
- `halt` --- сигнал останова
- `address` --- адрес перехода в памяти микрокоманд

### Цикл обработки инструкции
- Выборка инструкции
- Выборка операнда(включает в себя выборку адреса для инструкций взаимодействующих с памятью)
- Выполнение инструкции

### Особенности реализации процесса моделирования
- при запуске производится инициализация модели в функции `setup_machine_simulation()` (заполнение памяти микрокоманд и таблицы опкодов, создание объектов `DP` и `CU`)
- в `mIR` загружается инструкция по текущему адресу `mPC`
- по типу микрокоманды вызывается одна из двух функций обработки микрокоманд
- микрокоманда обрабатывается
- увеличивается счетчик тиков
- выполняется запись в журнал логов (если была заполнена конфигурация `step-by-step`)
- в случае превышения лимита исполнения или установления флага `running` в 0 процесс моделирования прерывается

Так как мы вынуждены вызывать функции сигналов к `DP` последовательно, они расположены в порядке от выхода из памяти, ко входу в память. Так же для того чтобы обеспечить одновременное защелкивание двух регистров на сигналы от друг друга (`acc` <-> `shadow_acc`) данные регистров изменяются по краю такта в функции `sync()`


## Тестирование

Осуществляется при помощи golden тестов. Всего реализовано 7 тестов для модели и транслятора:
- `cat` --- считывание из входного буфера устройства и вывод на выходной буфер
- `double_ariphmetics` --- сумма массива 32-битных чисел из входного файла в 64-битное число. 
- `hello` --- вывод 'hello world!' в выходной буфер устройства
- `hello_user_name` --- запрос у пользователя его имени, считывание, вывод приветствия
- `sort` --- сортировка вставкой для массива чисел из входных данных
- `prob2` --- вычисление задачи с [project euler](https://projecteuler.net/problem=6)
- `swap_demo` --- алгоритм демонстрирующий оптимизацию при помощи теневого регистра

Код тестов доступен в файлах [test_translator.py](/tests/test_translator.py) и [test_machine.py](/tests/test_machine.py).

Входные и выходные данные для каждого из тестов можно посмотреть в директории [golden](/tests/golden), также они доступны в директории [example](/example)

Конфигурация CI доступна в [python_ci.yaml](/.github/workflows/python_ci.yaml)

