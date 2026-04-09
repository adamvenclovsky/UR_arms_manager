# Programy

Každý robot může mít přiřazený jiný lokální `.script` soubor.

## Pravidlo pro první verzi

- programy se editují lokálně ve VS Code
- manager je jen přiřazuje a posílá do konkrétního robota přes socket
- první verze nepoužívá upload `.urp` projektů do robota

## Doporučení

- jeden adresář na robota
- malé, čitelné script soubory
- žádná sdílená globální magie mezi roboty
