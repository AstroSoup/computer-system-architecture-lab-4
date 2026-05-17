# Лабораторная работа №4 по дисциплине "Архитектура компьютера".

Выполнил: Горин Семён Дмитриевич \
Группа: P3208 \
Вариант: `asm | acc | neum | mc | tick | binary | stream | port | pstr | prob2 | superscalar`

## Язык программирования

Язык программирования ассемблера описанный в форме РБНФ:
TODO: add labels to the instruction defenitions
```
program            ::= { line }
line               ::= [ label ] [ operation ] [ comment ] "\n"

label              ::= label_name ":"

operation          ::= instruction | directive

directive          ::= section | org | data

section            ::= ".text" | ".data"
org                ::= ".org" (uint | hex)
data               ::= (".word" | ".byte") (int | hex | string)
string             ::= '"' { <any symbol except '"'> } '"'

instruction        ::= io_command (absolute_address | indirect_address)
                     | address_command{".b" | ".w"} (indirect_address | absolute_address | relative_address | immediate_value)
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
(* commands will be extended or cut down (who knows) *)
indirect_address   ::= [ "-" ] "(" addr_value ")" [ "+" ]    (* dereference: address given by label or literal *)
absolute_address   ::= "$" (uint | hex | label_name)
relative_address   ::= int | hex | label_name
immediate_value    ::= "#" (int | hex | label_name)
int                ::= [ "-" ] uint
hex                ::= "0x" { <any of "0-9 a-f A-F"> }-
uint               ::= { <any of "0-9"> }-
label_name         ::= <any of "a-z A-Z _"> { <any of "a-z A-Z 0-9 _"> }
comment            ::= ";" { <any symbol except "\n"> }
```

## Организация памяти

Память реализует Принстонскую модель организации памяти. Длина машинного слова -- 32 бита. 

## Система команд
Каждая команда занимает 1 машинное слово в памяти.

Разделим команды на 4 вида: адресные, безадресные, IO, и команды ветвления. 

Заметим что в безадресных командах нам не нужно хранить операнд или его адрес. Значит можем выделить 1 опкод для всех безадресных команд, а затем получать дополнительную информацию об операции из оставшихся битов данных, которые в адресных и командах ветвления были бы заняты операндом.

Команды ветвления: состоят из опкода и сдвига который необходимо прибавить к PC.

Адресные команды: состоят из опкода, режима адресации, и операнда (будь то адрес, смещение или число)

Режимы адресации:
    - относительная
    - абсолютная
    - косвенная
    - прямая загрузка операнда
Размер операнда:
    - байт
    - слово

Все байтовые инструкции расширяются нулем.

таким образом все режимы адресации можно записать 3 битами.



## Транслятор

TBD...

## Модель процессора

### Datapath

Процессор построен на базе аккумуляторной архитектуры с применением паттерна теневого регистра для уменьшения обращений к памяти и параллелезации записей в память. 

TODO: remove path from DR to SHADOW_AR since only time we stash data into shadow AR is with swap which comes from AR. We cant access shadow ar direcly similarly to the way we cant access shadow acc directly.


![Datapath scheme](assets/datapath/scheme.svg)

### Control Unit

TBD

## Тестирование

TBD...


