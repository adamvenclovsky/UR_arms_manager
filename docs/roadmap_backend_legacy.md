# Roadmap

## Fáze 0 — kostra a pracovní prostředí
Cíl:
- připravit repo
- rozběhnout instalaci
- připravit config robotů
- ověřit CLI skeleton

Výstup:
- funkční `uam robots list`

## Fáze 1 — jeden robot přes URSim
Cíl:
- připojit `robot1`
- číst základní stav z dashboard serveru
- přiřadit mu program
- spustit ho a zastavit

Výstup:
- funkční `status`, `assign`, `run`, `stop` nad jedním URSim

## Fáze 2 — více robotů nezávisle
Cíl:
- přidat `robot2` a `robot3`
- ověřit, že každý má jiný program
- ověřit, že příkazy jdou separátně

Výstup:
- 2–3 nezávisle řízené URSim instance

## Fáze 3 — lepší stav a diagnostika
Cíl:
- přidat periodický polling
- přidat detailnější stav
- přidat logování chyb a timeoutů

Výstup:
- spolehlivější základ pro další vrstvu

## Fáze 4 — lehké API
Cíl:
- nad CLI logikou přidat REST API
- nepřepsat architekturu, jen ji obalit

Výstup:
- centrální proces, který lze později napojit na UI

## Fáze 5 — editace programů a validace
Cíl:
- šablony programů
- základní validace script souborů
- lepší práce s programy per robot

Výstup:
- bezpečnější workflow pro úpravu programů

## Fáze 6 — RTDE monitoring
Cíl:
- doplnit detailnější telemetrii
- nechat dashboard pro high-level příkazy
- nechat script socket pro odesílání programu

Výstup:
- lepší stavová data bez velkého přepsání systému

## Fáze 7 — volitelný ROS 2 bridge
Cíl:
- přidat ROS 2 jen pokud už bude jasné, že to přináší hodnotu
- použít namespaces per robot
- držet ROS 2 jako samostatnou integrační vrstvu

Výstup:
- otevřená cesta k MoveIt / ros2_control bez zničení lehkého základu
