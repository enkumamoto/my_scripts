#!/bin/bash

BAT_PATH="/sys/class/power_supply"

BAT=$(ls $BAT_PATH | grep BAT | head -n 1)

if [ -z "$BAT" ]; then
    echo "❌ Nenhuma bateria encontrada no sistema."
    exit 1
fi

echo "🔎 Diagnóstico da bateria: $BAT"
echo "===================================================="

STATUS=$(cat $BAT_PATH/$BAT/status)
CAPACITY=$(cat $BAT_PATH/$BAT/capacity)

ENERGY_NOW=$(cat $BAT_PATH/$BAT/energy_now 2>/dev/null || cat $BAT_PATH/$BAT/charge_now)
ENERGY_FULL=$(cat $BAT_PATH/$BAT/energy_full 2>/dev/null || cat $BAT_PATH/$BAT/charge_full)
ENERGY_FULL_DESIGN=$(cat $BAT_PATH/$BAT/energy_full_design 2>/dev/null || cat $BAT_PATH/$BAT/charge_full_design)

HEALTH=$(echo "scale=2; ($ENERGY_FULL/$ENERGY_FULL_DESIGN)*100" | bc)

echo ""
echo "📊 INFORMAÇÕES BÁSICAS"
echo "----------------------------------"
echo "⚡ Status atual da bateria : $STATUS"
echo "🔋 Percentual atual        : $CAPACITY %"
echo "❤️ Saúde estimada          : $HEALTH %"

CYCLE_FILE="$BAT_PATH/$BAT/cycle_count"

if [ -f "$CYCLE_FILE" ]; then
    CYCLES=$(cat $CYCLE_FILE)
else
    CYCLES="N/A"
fi

echo "🔁 Ciclos de carga         : $CYCLES"

echo ""
echo "🧠 INTERPRETAÇÃO DOS RESULTADOS"
echo "===================================================="

# Explicação do status
echo ""
echo "🔌 STATUS DA BATERIA"
case $STATUS in
    Charging)
        echo "A bateria está carregando no momento."
        echo "Isso significa que o notebook está conectado à energia."
        ;;
    Discharging)
        echo "A bateria está sendo utilizada pelo notebook."
        echo "O sistema está consumindo energia da bateria."
        ;;
    Full)
        echo "A bateria está totalmente carregada."
        echo "O sistema provavelmente está funcionando direto na energia."
        ;;
    *)
        echo "Status não identificado pelo script."
        ;;
esac

# Explicação da capacidade
echo ""
echo "📦 CAPACIDADE DA BATERIA"

echo "Capacidade atual máxima registrada : $ENERGY_FULL"
echo "Capacidade original de fábrica     : $ENERGY_FULL_DESIGN"

echo ""

if (( $(echo "$HEALTH > 90" | bc -l) )); then
    echo "🟢 A bateria está muito próxima da capacidade original."
    echo "O desgaste é mínimo."
elif (( $(echo "$HEALTH > 75" | bc -l) )); then
    echo "🟡 Existe desgaste natural da bateria."
    echo "Isso é esperado após alguns anos de uso."
elif (( $(echo "$HEALTH > 60" | bc -l) )); then
    echo "🟠 A bateria já apresenta desgaste considerável."
    echo "A autonomia pode estar reduzida."
else
    echo "🔴 A capacidade da bateria está muito reduzida."
    echo "Pode ser recomendável substituir a bateria."
fi

echo ""
echo "🔁 CICLOS DE CARGA"

if [ "$CYCLES" != "N/A" ]; then

    echo "A bateria já passou por $CYCLES ciclos de carga."

    if [ "$CYCLES" -lt 300 ]; then
        echo "🟢 Número baixo de ciclos. A bateria ainda tem bastante vida útil."
    elif [ "$CYCLES" -lt 600 ]; then
        echo "🟡 Número moderado de ciclos. Desgaste natural esperado."
    elif [ "$CYCLES" -lt 900 ]; then
        echo "🟠 Número alto de ciclos. A bateria pode começar a perder autonomia."
    else
        echo "🔴 Número muito alto de ciclos. A bateria pode estar perto do fim da vida útil."
    fi

    echo ""
    echo "💡 O que é um ciclo de carga?"
    echo "Um ciclo representa o uso de 100% da capacidade da bateria."
    echo "Exemplo: usar 50% hoje e recarregar + usar mais 50% amanhã = 1 ciclo."

else
    echo "Este notebook não fornece contagem de ciclos de bateria."
fi

echo ""
echo "===================================================="
echo "Diagnóstico finalizado."