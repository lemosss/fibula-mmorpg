"""
npcs.py — Diálogo e comércio com NPCs.

NPCs respondem a quem fala a até 3 tiles de distância. Palavras-chave
especiais nas definições (data/npcs.json):
  __HEAL__   — cura o jogador (Padre Élio)
  __TRADE__  — abre a janela de comércio no cliente (Tobias)
"""
import unicodedata

from game import data

TALK_RANGE = 3

GREETINGS = ("oi", "ola", "hi", "hello", "salve", "bom dia", "boa tarde")
FAREWELLS = ("tchau", "bye", "adeus", "ate mais", "xau")


def normalize(text: str) -> str:
    """minúsculas + sem acentos, para casar palavras-chave."""
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def npc_in_range(game, player, name: str = None):
    """NPC mais próximo do jogador (ou um específico por nome) a <= 3 tiles."""
    best = None
    for npc in game.npcs.values():
        if name and npc.name != name:
            continue
        if npc.z != player.z:
            continue
        d = max(abs(npc.x - player.x), abs(npc.y - player.y))
        if d <= TALK_RANGE and (best is None or d < best[0]):
            best = (d, npc)
    return best[1] if best else None


def shop_payload(npc) -> dict:
    """Lista de compra/venda enviada ao cliente para a janela de comércio."""
    shop = npc.ndef.get("shop", {})
    sells = [
        {"id": i, "name": data.item_name(i), "price": data.item(i).get("priceBuy", 0)}
        for i in shop.get("sells", [])
    ]
    buys = [
        {"id": i, "name": data.item_name(i), "price": data.item(i).get("priceSell", 0)}
        for i in shop.get("buys", [])
    ]
    return {"type": "npc_trade", "npc": npc.name, "sells": sells, "buys": buys}


def handle_say(game, player, text: str) -> bool:
    """
    Tenta tratar a fala como conversa com um NPC próximo.
    Retorna True se algum NPC respondeu.
    """
    npc = npc_in_range(game, player)
    if npc is None:
        return False

    norm = normalize(text)
    dialog = npc.ndef.get("dialog", {})

    def reply(template: str):
        game.npc_say(npc, template.replace("%s", player.name))

    # saudação / despedida
    if any(norm.startswith(g) for g in GREETINGS):
        reply(dialog.get("greet", "Ola, %s."))
        return True
    if any(norm.startswith(f) for f in FAREWELLS):
        reply(dialog.get("farewell", "Adeus, %s."))
        return True

    # palavras-chave
    for entry in dialog.get("keywords", []):
        if any(k in norm for k in entry["k"]):
            action = entry["r"]
            if action == "__HEAL__":
                if player.hp >= player.maxhp:
                    reply("Voce nao esta ferido, %s.")
                else:
                    player.hp = player.maxhp
                    player.send(player.stats_payload())
                    game.broadcast_hp(player)
                    game.fx(player.x, player.y, player.z, kind="heal")
                    reply("Que os deuses te abencoem, %s!")
            elif action == "__TRADE__":
                reply("Aqui estao minhas mercadorias, %s.")
                player.send(shop_payload(npc))
            else:
                reply(action)
            return True
    return False


# --------------------------------------------------------------- comércio

def buy(game, player, npc_name: str, item_id: int, count: int) -> str:
    """Compra do NPC. Retorna mensagem de erro ou '' em caso de sucesso."""
    npc = npc_in_range(game, player, npc_name)
    if npc is None:
        return "Aproxime-se do NPC para negociar."
    shop = npc.ndef.get("shop", {})
    if item_id not in shop.get("sells", []):
        return "Esse item nao esta a venda."
    count = max(1, min(100, int(count)))
    price = data.item(item_id).get("priceBuy", 0) * count
    if player.inv_count(1) < price:
        return "Voce nao tem ouro suficiente."
    # tenta entregar primeiro; só então cobra (give é tudo-ou-nada)
    err = game.give(player, item_id, count)
    if err:
        return err
    player.inv_remove(1, price)
    game.npc_say(npc, f"Aqui esta: {count}x {data.item_name(item_id)}.")
    return ""


def sell(game, player, npc_name: str, item_id: int, count: int) -> str:
    """Venda ao NPC. Retorna mensagem de erro ou '' em caso de sucesso."""
    npc = npc_in_range(game, player, npc_name)
    if npc is None:
        return "Aproxime-se do NPC para negociar."
    shop = npc.ndef.get("shop", {})
    if item_id not in shop.get("buys", []):
        return "Nao compro esse item."
    count = max(1, min(100, int(count)))
    if player.inv_count(item_id) < count:
        # itens equipados NÃO contam: precisa desequipar antes de vender
        equipped = any(it and it["id"] == item_id
                       for it in player.equipment.values())
        if equipped:
            return "Desequipe o item antes de vender."
        return "Voce nao tem esse item."
    price = data.item(item_id).get("priceSell", 0) * count
    player.inv_remove(item_id, count)
    if not player.inv_add(1, price):
        # mochila cheia de itens não-empilháveis: devolve a mercadoria
        player.inv_add(item_id, count)
        return "Sem espaco para receber o ouro."
    game.npc_say(npc, f"Negocio fechado: {price} moedas de ouro.")
    return ""
