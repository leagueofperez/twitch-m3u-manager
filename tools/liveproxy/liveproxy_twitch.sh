#!/bin/bash

twitch_base_url="https://twitch.tv"
DEFAULT_M3U="twitch.m3u"
TAB=$'\t'

DEFAULT_SERVER="http://127.0.0.1:8000/liveproxy"
SERVER_URL=""
M3U_FILE=""

# ---------- Utilidades ----------

# Pide la URL base del servidor LiveProxy (http/https, con o sin puerto, con o sin ruta).
# Ejemplos: http://127.0.0.1:53422 | https://proxy.midominio.com | https://midominio.com/liveproxy
# Resultado en la variable global SERVER_URL (sin barra final).
ask_server() {
	local default="${SERVER_URL:-$DEFAULT_SERVER}" input
	while true; do
		read -rp "Servidor LiveProxy [${default}]: " input || exit 1
		input=${input:-$default}
		input="${input%"${input##*[![:space:]]}"}" # quitar espacios finales
		if [[ ! "$input" =~ ^[a-zA-Z][a-zA-Z0-9+.-]*:// ]]; then
			input="http://${input}" # sin esquema -> http://
			echo "  (sin esquema, se asume http://)"
		fi
		if [[ "$input" =~ ^https?://[^/[:space:]]+(/.*)?$ ]]; then
			SERVER_URL="${input%/}"
			while [[ "$SERVER_URL" == */ ]]; do SERVER_URL="${SERVER_URL%/}"; done
			return 0
		fi
		echo "URL no valida. Usa http:// o https:// (puerto y ruta opcionales)."
	done
}

# Genera la URL de LiveProxy para un canal
gen_url() {
	local channel="$1" command encoded
	command="streamlink ${twitch_base_url}/${channel} best"
	encoded=$(printf '%s' "$command" | base64 | tr -d '\n')
	printf '%s/base64/%s/' "$SERVER_URL" "$encoded"
}

# Lee un .m3u y lo convierte a lineas "nombre<TAB>url"
read_m3u() {
	awk '
        /^#EXTINF/ { sub(/^#EXTINF:[^,]*,/, ""); name=$0; sub(/\r$/, "", name); next }
        /^[^#]/ && NF { if (name != "") { sub(/\r$/, ""); print name "\t" $0; name="" } }
    ' "$1"
}

# Escribe un .m3u ordenado alfabeticamente desde stdin ("nombre<TAB>url")
write_m3u() {
	local file="$1"
	{
		echo "#EXTM3U"
		sort -f -t "$TAB" -k1,1 -u | while IFS="$TAB" read -r name url; do
			printf '#EXTINF:-1,%s\n%s\n' "$name" "$url"
		done
	} >"$file"
}

# Selecciona la lista (.m3u) de trabajo. Resultado en la variable global M3U_FILE.
select_list() {
	local -a files=()
	local f input i default="${M3U_FILE:-$DEFAULT_M3U}"
	for f in *.m3u *.m3u8; do
		[[ -f "$f" ]] && files+=("$f")
	done
	clear
	echo "=== Seleccion de lista (.m3u) ==="
	if ((${#files[@]} > 0)); then
		echo "Listas encontradas en $(pwd):"
		for i in "${!files[@]}"; do
			printf '  %2d) %s\n' $((i + 1)) "${files[$i]}"
		done
	else
		echo "No hay listas .m3u en $(pwd)."
	fi
	echo
	read -rp "Numero, o nombre de archivo (nuevo o existente) [${default}]: " input || exit 0
	if [[ -z "$input" ]]; then
		M3U_FILE="$default"
	elif [[ "$input" =~ ^[0-9]+$ ]] && ((input >= 1 && input <= ${#files[@]})); then
		M3U_FILE="${files[$((input - 1))]}"
	else
		[[ "$input" != *.m3u && "$input" != *.m3u8 ]] && input="${input}.m3u"
		M3U_FILE="$input"
	fi
}

# Texto con la lista actual y su estado
list_info() {
	if [[ -f "$M3U_FILE" ]]; then
		printf 'Lista actual: %s (%s canal(es))' "$M3U_FILE" "$(grep -c '^#EXTINF' "$M3U_FILE")"
	else
		printf 'Lista actual: %s (no existe todavia, usa la opcion 2 para crearla)' "$M3U_FILE"
	fi
}

require_file() {
	if [[ ! -f "$1" ]]; then
		echo "El archivo '$1' no existe."
		return 1
	fi
}

# Muestra los canales del .m3u y deja elegir uno por numero.
# Resultado en la variable global PICKED. Devuelve 1 si se cancela o no hay canales.
pick_channel() {
	local file="$1" choice i
	local -a names
	mapfile -t names < <(read_m3u "$file" | cut -f1)
	if ((${#names[@]} == 0)); then
		echo "La lista '$file' no contiene canales."
		return 1
	fi
	echo "Canales disponibles en $file:"
	for i in "${!names[@]}"; do
		printf '  %2d) %s\n' $((i + 1)) "${names[$i]}"
	done
	echo "   0) Cancelar"
	while true; do
		read -rp "Selecciona un numero: " choice || exit 1
		if [[ "$choice" == "0" ]]; then
			echo "Cancelado."
			return 1
		elif [[ "$choice" =~ ^[0-9]+$ ]] && ((choice >= 1 && choice <= ${#names[@]})); then
			PICKED="${names[$((choice - 1))]}"
			return 0
		fi
		echo "Opcion no valida."
	done
}

# Pausa hasta pulsar una tecla y limpia la pantalla
pause_continue() {
	echo
	read -rsn1 -p "Pulsa una tecla para continuar..." || exit 0
	clear
}

# ---------- Opciones ----------

# 1) URL individual
opt_single_url() {
	local channel
	ask_server
	read -rp "Twitch username: " channel
	[[ -z "$channel" ]] && {
		echo "Canal vacio."
		return
	}
	printf 'LiveProxy URL: %s\n' "$(gen_url "${channel,,}")"
}

# 2) Generar .m3u ordenada
opt_generate_m3u() {
	local file input channel entries=""
	file="$M3U_FILE"
	if [[ -f "$file" ]]; then
		read -rp "'$file' ya existe. Sobrescribir? [s/N]: " ans
		[[ "${ans,,}" != "s" ]] && {
			echo "Cancelado."
			return
		}
	fi
	ask_server
	echo "Introduce los canales separados por comas o espacios:"
	read -r input
	input=${input//,/ }
	for channel in $input; do
		entries+="${channel}${TAB}$(gen_url "${channel,,}")"$'\n'
	done
	if [[ -z "$entries" ]]; then
		echo "No se introdujeron canales."
		return
	fi
	printf '%s' "$entries" | write_m3u "$file"
	echo "Generado: $file ($(grep -c "^#EXTINF" "$file") canal(es))"
}

# 3.1) Anadir canal(es) y ordenar
opt_add_channel() {
	local file input channel current new_entries="" added=0
	file="$M3U_FILE"
	require_file "$file" || return
	echo "Canales a anadir (separados por comas o espacios, ej: canal1,canal2,canal3):"
	read -r input
	input=${input//,/ }
	[[ -z "${input// /}" ]] && {
		echo "No se introdujeron canales."
		return
	}

	current=$(read_m3u "$file")
	ask_server

	for channel in $input; do
		if printf '%s\n%s' "$current" "$new_entries" | cut -f1 | grep -qixF -- "$channel"; then
			echo "'$channel' ya existe, se omite (usa 3.2 para actualizar su URL)."
			continue
		fi
		new_entries+="${channel}${TAB}$(gen_url "${channel,,}")"$'\n'
		added=$((added + 1))
	done

	if ((added == 0)); then
		echo "No se anadio ningun canal."
		return
	fi

	{
		[[ -n "$current" ]] && printf '%s\n' "$current"
		printf '%s' "$new_entries"
	} | write_m3u "$file"
	echo "$added canal(es) anadido(s) y lista ordenada: $file"
}

# 3.2) Actualizar URL de un canal (elegido de la lista)
opt_update_channel() {
	local file current newurl
	file="$M3U_FILE"
	require_file "$file" || return
	pick_channel "$file" || return

	ask_server
	newurl=$(gen_url "${PICKED,,}")
	current=$(read_m3u "$file")
	printf '%s\n' "$current" |
		awk -F'\t' -v OFS='\t' -v n="$PICKED" -v u="$newurl" \
			'$1==n{$2=u} {print}' |
		write_m3u "$file"
	echo "URL de '$PICKED' actualizada en $file"
}

# 3.3) Eliminar un canal (elegido de la lista)
opt_delete_channel() {
	local file current ans
	file="$M3U_FILE"
	require_file "$file" || return
	pick_channel "$file" || return

	read -rp "Eliminar '$PICKED' de $file? [s/N]: " ans
	[[ "${ans,,}" != "s" ]] && {
		echo "Cancelado."
		return
	}

	current=$(read_m3u "$file")
	printf '%s\n' "$current" |
		awk -F'\t' -v n="$PICKED" '$1!=n' |
		write_m3u "$file"
	echo "Canal '$PICKED' eliminado de $file"
}

# 3.4) Cambiar el servidor de todos los enlaces del .m3u
opt_change_server() {
	local file current ans
	file="$M3U_FILE"
	require_file "$file" || return
	current=$(read_m3u "$file")
	if [[ -z "$current" ]]; then
		echo "La lista '$file' no contiene canales."
		return
	fi
	ask_server
	read -rp "Cambiar el servidor de todos los enlaces de $file a $SERVER_URL ? [s/N]: " ans
	[[ "${ans,,}" != "s" ]] && {
		echo "Cancelado."
		return
	}

	# Conserva la parte /base64/<comando>/ de cada enlace y sustituye solo el servidor
	printf '%s\n' "$current" |
		awk -F'\t' -v OFS='\t' -v srv="$SERVER_URL" '
            { i = index($2, "/base64/"); if (i > 0) $2 = srv substr($2, i); print }' |
		write_m3u "$file"
	echo "Servidor actualizado en $(grep -c '^#EXTINF' "$file") canal(es): $file"
}

submenu_update() {
	local sub
	while true; do
		clear
		echo "--- Actualizar .m3u existente ---"
		list_info
		echo
		echo
		echo "1) Anadir canal(es) y ordenar"
		echo "2) Actualizar URL de un canal"
		echo "3) Eliminar un canal"
		echo "4) Cambiar servidor de todos los enlaces"
		echo "9) Volver al menu principal"
		echo "0) Salir"
		read -rp "Opcion: " sub || exit 0
		case "$sub" in
		1) opt_add_channel ;;
		2) opt_update_channel ;;
		3) opt_delete_channel ;;
		4) opt_change_server ;;
		9) return ;;
		0)
			echo "Hasta luego."
			exit 0
			;;
		*) echo "Opcion no valida." ;;
		esac
		pause_continue
	done
}

# ---------- Menu principal ----------

select_list

while true; do
	clear
	echo "=== LiveProxy Twitch ==="
	list_info
	echo
	echo
	echo "1) Generar URL individual"
	echo "2) Generar .m3u ordenada alfabeticamente por nombre del canal"
	echo "3) Actualizar .m3u existente"
	echo "4) Cambiar lista"
	echo "0) Salir"
	read -rp "Opcion: " opt || exit 0
	case "$opt" in
	1) opt_single_url ;;
	2) opt_generate_m3u ;;
	3)
		submenu_update
		continue
		;;
	4)
		select_list
		continue
		;;
	0)
		echo "Hasta luego."
		exit 0
		;;
	*) echo "Opcion no valida." ;;
	esac
	pause_continue
done
