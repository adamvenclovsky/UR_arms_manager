# UR_arms_manager

Lehký centrální manager pro 2–3 Universal Robots (URSim i fyzická ramena), postavený primárně v Pythonu.

## Cíl první verze

- evidovat roboty (`robot1`, `robot2`, `robot3`)
- přiřazovat každému robotu jiný lokální URScript program
- spouštět a zastavovat roboty nezávisle
- číst základní stav robota
- programy editovat lokálně ve VS Code
- testovat vše nejdřív nad URSim

## Proč je první verze bez ROS 2

První verze je záměrně malá:
- nižší nároky na notebook
- kratší cesta k funkčnímu výsledku
- jednodušší ladění socket komunikace s URSim
- ROS 2 můžeme přidat až jako další vrstvu, ne jako základ

## Navržený princip

Každý robot má:
- vlastní konfiguraci (`config/robots.yaml`)
- vlastní přiřazený program (`assigned_program`)
- vlastní socket připojení pro dashboard příkazy a posílání scriptu

Centrální aplikace:
- načte seznam robotů
- dovolí program přiřadit
- umí poslat script do konkrétního robota
- umí robota zastavit
- umí vrátit základní stav přes dashboard server

## Rychlý start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp config/robots.example.yaml config/robots.yaml
```

Uprav `config/robots.yaml` podle portů tvých URSim instancí.

## Příklady použití

```bash
uam robots list
uam robot status robot1
uam robot assign robot1 programs/robot1/demo_hello.script
uam robot run robot1
uam robot stop robot1
```

## Doporučené mapování portů pro více URSim instancí

Příklad pro 2 simulátory běžící na jednom notebooku:
- robot1: dashboard `29991`, script `30021`
- robot2: dashboard `29992`, script `30022`
- robot3: dashboard `29993`, script `30023`

Repo na to myslí: porty jsou konfigurovatelné pro každý robot zvlášť.

## Další kroky

1. Rozběhnout CLI nad jedním URSim.
2. Ověřit `status`, `assign`, `run`, `stop`.
3. Přidat polling stavu a jednoduchý REST API layer.
4. Přidat RTDE monitoring.
5. Teprve potom řešit ROS 2 integraci.
