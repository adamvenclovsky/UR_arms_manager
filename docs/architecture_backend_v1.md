# Architektura v1

## Hlavní rozhodnutí

První verze bude **Python-only, bez povinného ROS 2**.

Důvod:
- chceme rychlý první funkční výsledek
- chceme nízké HW nároky
- chceme vše otestovat nad URSim
- nechceme se hned zamotat do ROS 2 ekosystému

## Vrstvy

### 1. Domain / model vrstva
Obsahuje čisté modely:
- `RobotConfig`
- `RobotStatus`
- přiřazený program

Tato vrstva neřeší síť ani sockety.

### 2. Registry / konfigurace
Starost o:
- seznam robotů
- porty
- přiřazené programy
- persistenci do YAML

### 3. UR adapter vrstva
Starost o komunikaci s UR:
- dashboard server
- posílání URScript programu přes socket

### 4. Service vrstva
Starost o aplikační logiku:
- získej stav
- spusť přiřazený program
- zastav program

### 5. Interface vrstva
Pro v1 jen:
- CLI

Později:
- REST API
- jednoduché web UI
- případně ROS 2 bridge

## Nezávislost robotů
Každý robot má:
- vlastní konfiguraci
- vlastní přiřazený program
- vlastní manager instanci
- vlastní socket komunikaci

To je důležité, aby šel každý robot řídit nezávisle.

## Programový model v1
Program = lokální `.script` soubor v repozitáři.

To znamená:
- editace ve VS Code
- verzování přes Git
- jednoduché nasazení do URSim i na reálný robot
- žádná nutnost ruční editace na teach pendantu

## Co zatím neděláme
V první verzi neděláme:
- složitý scheduler
- databázi
- web frontend framework navíc
- MoveIt
- multi-robot motion planning
- synchronizaci ramen mezi sebou
- upload `.urp` projektů do interního úložiště robota

## Co přidáme později
- RTDE polling pro lepší stav
- background worker pro průběžný monitoring
- REST API
- jednoduché web UI
- ROS 2 adapter jako volitelnou vrstvu
