import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
import datetime
import aiohttp
import re
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from functools import wraps
import threading
from dotenv import load_dotenv
from database import *

# Загрузка переменных окружения из .env файла
load_dotenv()

# Инициализация базы данных
init_database()

# ==========================================
# --- НАСТРОЙКИ ---
# ==========================================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

OWNER_ID = 1188003420406304848
CO_OWNER_ID = 1190827838526476321

MAIN_SERVER_ID = 1491493901184270588
AUTO_ROLE_ID = 1482501487841116183

UI_COLOR = 0x2b2d31
RED_COLOR = 0xdd2e44

# ==========================================
# --- ДИЗАЙН ---
# ==========================================
async def reply_ok(ctx, text):
    await ctx.send(f"> ( + ) {text}")

async def reply_err(ctx, text):
    await ctx.send(f"> ( - ) {text}")

async def reply_info(ctx, text):
    return await ctx.send(f"> ( ⏳ ) {text}")

@bot.check
async def require_main_server(ctx):
    # Владельцы могут использовать команды везде
    if ctx.author.id in [OWNER_ID, CO_OWNER_ID]:
        return True
    # Если MAIN_SERVER_ID не установлен, команды доступны везде
    if MAIN_SERVER_ID == 0:
        return True
    # Все остальные тоже могут использовать команды
    return True

# ==========================================
# --- БАЗЫ ДАННЫХ (SQLite через обертки) ---
# ==========================================

# Обертки для совместимости со старым кодом
class DBList:
    """Список-обертка для работы с БД"""
    def __init__(self, guild_id, get_func, add_func, remove_func):
        self.guild_id = str(guild_id)
        self.get_func = get_func
        self.add_func = add_func
        self.remove_func = remove_func
    
    def __iter__(self):
        return iter(self.get_func(self.guild_id))
    
    def __contains__(self, item):
        return item in self.get_func(self.guild_id)
    
    def append(self, item):
        if item not in self:
            self.add_func(self.guild_id, item)
    
    def remove(self, item):
        if item in self:
            self.remove_func(self.guild_id, item)

class DBDictOfLists:
    """Словарь списков для whitelist/blacklist/protected"""
    def __init__(self, get_func, add_func, remove_func):
        self.get_func = get_func
        self.add_func = add_func
        self.remove_func = remove_func
    
    def __getitem__(self, guild_id):
        return DBList(guild_id, self.get_func, self.add_func, self.remove_func)
    
    def __contains__(self, guild_id):
        return True

class DBDictOfDicts:
    """Словарь словарей для access/stable_roles/bans"""
    def __init__(self, get_func, set_func, del_func):
        self.get_func = get_func
        self.set_func = set_func
        self.del_func = del_func
    
    def __getitem__(self, guild_id):
        return DBDictInner(str(guild_id), self.get_func, self.set_func, self.del_func)
    
    def __contains__(self, guild_id):
        return True

class DBDictInner:
    """Внутренний словарь для конкретной гильдии"""
    def __init__(self, guild_id, get_func, set_func, del_func):
        self.guild_id = guild_id
        self.get_func = get_func
        self.set_func = set_func
        self.del_func = del_func
    
    def __getitem__(self, key):
        data = self.get_func(self.guild_id)
        return data.get(str(key))
    
    def __setitem__(self, key, value):
        self.set_func(self.guild_id, str(key), value)
    
    def __delitem__(self, key):
        self.del_func(self.guild_id, str(key))
    
    def __contains__(self, key):
        data = self.get_func(self.guild_id)
        return str(key) in data
    
    def get(self, key, default=None):
        data = self.get_func(self.guild_id)
        return data.get(str(key), default)
    
    def items(self):
        return self.get_func(self.guild_id).items()
    
    def copy(self):
        """Возвращает копию словаря"""
        return self.get_func(self.guild_id).copy()
    
    def keys(self):
        """Возвращает ключи словаря"""
        return self.get_func(self.guild_id).keys()
    
    def values(self):
        """Возвращает значения словаря"""
        return self.get_func(self.guild_id).values()

# Инициализация "словарей" для доступа к БД
USER_ACCESS = DBDictOfDicts(
    get_access,
    lambda gid, uid, lvl: add_access(gid, uid, lvl),
    lambda gid, uid: remove_access(gid, uid)
)

WHITELIST_IDS = DBDictOfLists(
    get_whitelist,
    add_to_whitelist,
    remove_from_whitelist
)

BLACKLIST_IDS = DBDictOfLists(
    get_blacklist,
    add_to_blacklist,
    remove_from_blacklist
)

PROTECTED_USERS = DBDictOfLists(
    get_protected,
    add_to_protected,
    remove_from_protected
)

STABLE_ROLES = DBDictOfDicts(
    get_stable_roles,
    set_stable_role,
    remove_stable_role
)

TEMP_BANS = DBDictOfDicts(
    get_temp_bans,
    add_temp_ban,
    remove_temp_ban
)

A_TEMP_BANS = DBDictOfDicts(
    get_hard_bans,
    add_hard_ban,
    remove_hard_ban
)

class LogChannelsDict:
    def __getitem__(self, guild_id):
        return get_log_channel(str(guild_id))
    def __contains__(self, guild_id):
        return get_log_channel(str(guild_id)) is not None
    def __setitem__(self, guild_id, channel_id):
        set_log_channel(str(guild_id), str(channel_id))

LOG_CHANNELS = LogChannelsDict()

class AutoRolesDict:
    def __getitem__(self, guild_id):
        return get_auto_role(str(guild_id))
    def __setitem__(self, guild_id, value):
        enabled = value.get('enabled', False)
        role_id = value.get('role_id')
        set_auto_role(str(guild_id), enabled, role_id)

AUTO_ROLES = AutoRolesDict()

def get_g_dict(data_dict, guild_id):
    """Получить словарь для гильдии"""
    return data_dict[guild_id]

def get_g_list(data_dict, guild_id):
    """Получить список для гильдии"""
    return data_dict[guild_id]

def load_data(file, default):
    """Загрузить данные из JSON файла (только для бэкапов)"""
    if not os.path.exists(file):
        return default
    try:
        with open(file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default

def save_backup(file, data):
    """Сохранить бэкап в JSON файл"""
    try:
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

# ==========================================
# --- АНТИРЕЙД ЗАЩИТА ---
# ==========================================
BAN_TRACKER = {}  # {guild_id: {user_id: [timestamps]}}

def track_ban(guild_id, user_id):
    """Отслеживает баны и возвращает True если превышен лимит"""
    now = datetime.datetime.now()
    gid = str(guild_id)
    uid = str(user_id)
    
    if gid not in BAN_TRACKER:
        BAN_TRACKER[gid] = {}
    if uid not in BAN_TRACKER[gid]:
        BAN_TRACKER[gid][uid] = []
    
    # Удаляем старые баны (старше 1 минуты)
    BAN_TRACKER[gid][uid] = [t for t in BAN_TRACKER[gid][uid] if (now - t).seconds < 60]
    
    # Добавляем текущий бан
    BAN_TRACKER[gid][uid].append(now)
    
    # Проверяем лимит (5 банов за минуту)
    return len(BAN_TRACKER[gid][uid]) >= 5

# ==========================================
# --- ФУНКЦИЯ ЛОГИРОВАНИЯ ---
# ==========================================
async def send_log(guild, title, description, color=UI_COLOR):
    gid = str(guild.id)
    if gid in LOG_CHANNELS:
        ch_id = LOG_CHANNELS[gid]
        ch = guild.get_channel(ch_id)
        if ch:
            emb = discord.Embed(title=title, description=description, color=color)
            emb.set_footer(text=f"Time: {datetime.datetime.now().strftime('%H:%M:%S')}")
            try: 
                await ch.send(embed=emb)
            except: 
                pass

# ==========================================
# --- СПИСКИ ДОСТУПА И ВАЙТЛИСТА ---
# ==========================================
def load_txt_list(filename):
    """Загрузка списка ID из txt файла"""
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, "r", encoding='utf-8') as f:
            return [int(line.strip()) for line in f if line.strip()]
    except:
        return []

def load_hardcoded_users(filename):
    """Загрузка словаря пользователей из txt файла (формат: id:level)"""
    if not os.path.exists(filename):
        return {}
    try:
        result = {}
        with open(filename, "r", encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    uid, lvl = line.split(':', 1)
                    result[uid.strip()] = lvl.strip()
        return result
    except:
        return {}

def load_revoked_users(filename):
    """Загрузка списка отозванных пользователей из txt файла"""
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, "r", encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []

HARDCODED_USERS = load_hardcoded_users("hardcoded_users.txt")
WL_ONLY_USERS = load_txt_list("wl_only_users.txt")
REVOKED_USERS = load_revoked_users("revoked_users.txt")

if MAIN_SERVER_ID != 0:
    main_gid = str(MAIN_SERVER_ID)
    if main_gid not in USER_ACCESS: USER_ACCESS[main_gid] = {}
    if main_gid not in WHITELIST_IDS: WHITELIST_IDS[main_gid] = []

    # Удаление отозванных пользователей
    for r_uid in REVOKED_USERS:
        if r_uid in USER_ACCESS[main_gid]:
            del USER_ACCESS[main_gid][r_uid]
        if int(r_uid) in WHITELIST_IDS[main_gid]:
            WHITELIST_IDS[main_gid].remove(int(r_uid))

    # Добавление хардкоженных пользователей
    for uid, lvl in HARDCODED_USERS.items(): 
        USER_ACCESS[main_gid][uid] = lvl
        
    # Добавление пользователей в вайтлист
    for uid in WL_ONLY_USERS:
        if uid not in WHITELIST_IDS[main_gid]: 
            WHITELIST_IDS[main_gid].append(uid)

def get_lvl(guild_id, uid):
    if int(uid) in [OWNER_ID, CO_OWNER_ID]: return 3
    if not guild_id: return 0
    guild_access = get_g_dict(USER_ACCESS, guild_id)
    lvl_name = guild_access.get(str(uid), "none")
    return {"low": 1, "mid": 2, "pusy": 3}.get(lvl_name, 0)

# ==========================================
# --- БЫСТРЫЙ ANTI-NUKE ---
# ==========================================
nuke_tracker = {}

async def check_nuke_threat(guild, user, action_name):
    wl = get_g_list(WHITELIST_IDS, guild.id)
    if user.id == bot.user.id or user.id in [OWNER_ID, CO_OWNER_ID] or user.id in wl:
        return False
    now = datetime.datetime.now()
    if user.id not in nuke_tracker: 
        nuke_tracker[user.id] = []
    nuke_tracker[user.id] = [t for t in nuke_tracker[user.id] if (now - t).total_seconds() < 8]
    nuke_tracker[user.id].append(now)
    
    if len(nuke_tracker[user.id]) >= 3:
        try:
            await guild.ban(user, reason=f"Anti-Nuke: лимит ({action_name})")
            nuke_tracker[user.id] = []
            await send_log(guild, "Anti-Nuke", f"{user.mention} забанен: {action_name}", RED_COLOR)
            return True
        except: 
            pass
    return False

async def get_audit_actor(guild, action, target_id, max_retries=5):
    for _ in range(max_retries):
        try:
            async for entry in guild.audit_logs(limit=3, action=action):
                if entry.target.id == target_id:
                    if (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                        return entry.user
        except: 
            pass
        await asyncio.sleep(0.1)
    return None

@bot.event
async def on_member_ban(guild, user):
    actor = await get_audit_actor(guild, discord.AuditLogAction.ban, user.id)
    if actor:
        wl = get_g_list(WHITELIST_IDS, guild.id)
        
        # Проверка антирейда для вайтлиста (кроме владельцев)
        if actor.id in wl and actor.id not in [OWNER_ID, CO_OWNER_ID]:
            if track_ban(guild.id, actor.id):
                # Превышен лимит - снимаем вайтлист и баним
                wl.remove(actor.id)
                
                # Добавляем в apusy бан
                end = datetime.datetime.now() + datetime.timedelta(days=999)
                end_str = end.strftime("%d.%m.%Y %H:%M:%S")
                g_abans = get_g_dict(A_TEMP_BANS, guild.id)
                g_abans[str(actor.id)] = end_str
                
                try:
                    await guild.ban(actor, reason="Anti-Raid: массовые баны (5+ за минуту)")
                    await send_log(guild, "Anti-Raid (Массовые баны)", 
                                 f"{actor.mention} забанил 5+ человек за минуту.\nВайтлист снят, выдан APusy бан.", RED_COLOR)
                except:
                    pass
                return
        
        if actor.id != bot.user.id and actor.id not in wl and actor.id not in [OWNER_ID, CO_OWNER_ID]:
            try:
                await guild.ban(actor, reason="Anti-Nuke: бан без вайтлиста")
                await guild.unban(user, reason="Anti-Nuke: отмена бана")
                await send_log(guild, "Anti-Nuke (Ban)", f"{actor.mention} забанил {user.mention} без прав. \nНарушитель забанен, жертва разбанена.", RED_COLOR)
            except: 
                pass

@bot.event
async def on_member_remove(member):
    guild = member.guild
    actor = await get_audit_actor(guild, discord.AuditLogAction.kick, member.id)
    if actor:
        wl = get_g_list(WHITELIST_IDS, guild.id)
        if actor.id != bot.user.id and actor.id not in wl and actor.id not in [OWNER_ID, CO_OWNER_ID]:
            try:
                await guild.ban(actor, reason="Anti-Nuke: кик без вайтлиста")
                await send_log(guild, "Anti-Nuke (Kick)", f"{actor.mention} кикнул {member.mention} без прав. \nНарушитель забанен.", RED_COLOR)
            except: 
                pass

@bot.event
async def on_guild_channel_delete(channel):
    async def process():
        guild = channel.guild
        actor = await get_audit_actor(guild, discord.AuditLogAction.channel_delete, channel.id)
        wl = get_g_list(WHITELIST_IDS, guild.id)
        if actor and actor.id != bot.user.id and actor.id not in wl and actor.id not in [OWNER_ID, CO_OWNER_ID]:
            is_nuker = await check_nuke_threat(guild, actor, "Удаление каналов")
            try:
                await channel.clone(reason="Anti-Nuke: восстановление канала")
                if not is_nuker:
                    await guild.ban(actor, reason="Anti-Nuke: удаление каналов")
                    await send_log(guild, "Anti-Nuke (Каналы)", f"{actor.mention} удалил канал #{channel.name} без прав. \nКанал восстановлен, нарушитель забанен.", RED_COLOR)
            except: 
                pass
    asyncio.create_task(process())

@bot.event
async def on_guild_channel_create(channel):
    async def process():
        guild = channel.guild
        actor = await get_audit_actor(guild, discord.AuditLogAction.channel_create, channel.id)
        wl = get_g_list(WHITELIST_IDS, guild.id)
        if actor and actor.id != bot.user.id and actor.id not in wl and actor.id not in [OWNER_ID, CO_OWNER_ID]:
            is_nuker = await check_nuke_threat(guild, actor, "Спам каналами")
            try:
                await channel.delete(reason="Anti-Nuke: удаление спам-канала")
                if not is_nuker:
                    await guild.ban(actor, reason="Anti-Nuke: создание каналов")
                    await send_log(guild, "Anti-Nuke (Каналы)", f"{actor.mention} создал канал #{channel.name} без прав. \nКанал удален, нарушитель забанен.", RED_COLOR)
            except: 
                pass
    asyncio.create_task(process())

@bot.event
async def on_guild_role_delete(role):
    async def process():
        guild = role.guild
        actor = await get_audit_actor(guild, discord.AuditLogAction.role_delete, role.id)
        wl = get_g_list(WHITELIST_IDS, guild.id)
        if actor and actor.id != bot.user.id and actor.id not in wl and actor.id not in [OWNER_ID, CO_OWNER_ID]:
            is_nuker = await check_nuke_threat(guild, actor, "Удаление ролей")
            try:
                await guild.create_role(name=role.name, permissions=role.permissions, color=role.color, hoist=role.hoist, mentionable=role.mentionable, reason="Anti-Nuke: восстановление роли")
                if not is_nuker:
                    await guild.ban(actor, reason="Anti-Nuke: удаление ролей")
                    await send_log(guild, "Anti-Nuke (Роли)", f"{actor.mention} удалил роль @{role.name} без прав. \nРоль восстановлена, нарушитель забанен.", RED_COLOR)
            except: 
                pass
    asyncio.create_task(process())

@bot.event
async def on_webhooks_update(channel):
    async def process():
        guild = channel.guild
        wl = get_g_list(WHITELIST_IDS, guild.id)
        actor = await get_audit_actor(guild, discord.AuditLogAction.webhook_create, channel.id)
        if actor and actor.id != bot.user.id and actor.id not in wl and actor.id not in [OWNER_ID, CO_OWNER_ID]:
            await check_nuke_threat(guild, actor, "Создание вебхуков")
            try:
                await guild.ban(actor, reason="Anti-Nuke: вебхуки")
                await send_log(guild, "Anti-Nuke (Вебхуки)", f"{actor.mention} создал вебхук в {channel.mention} без прав. \nНарушитель забанен.", RED_COLOR)
            except: 
                pass
    asyncio.create_task(process())

# ==========================================
# ВХОД И БЭКАПЫ РОЛЕЙ
# ==========================================
@bot.event
async def on_member_join(member):
    if member.bot:
        try: 
            await member.ban(reason="Anti-Nuke: краш-бот")
        except: 
            pass
        
        actor = await get_audit_actor(member.guild, discord.AuditLogAction.bot_add, member.id)
        wl = get_g_list(WHITELIST_IDS, member.guild.id)
        
        if actor and actor.id != bot.user.id and actor.id not in wl and actor.id not in [OWNER_ID, CO_OWNER_ID]:
            try: 
                await member.guild.ban(actor, reason="Anti-Nuke: боты")
                await send_log(member.guild, "Anti-Nuke (Боты)", f"{actor.mention} добавил бота {member.mention}. \nБот и нарушитель забанены.", RED_COLOR)
            except: 
                pass
        return

    # Автороль для новых участников
    auto_roles = get_g_dict(AUTO_ROLES, member.guild.id)
    if auto_roles.get('enabled') and auto_roles.get('role_id'):
        role = member.guild.get_role(int(auto_roles['role_id']))
        if role and role < member.guild.me.top_role:
            try:
                await member.add_roles(role, reason="Автороль при входе")
                await send_log(member.guild, "Автороль", f"Выдана роль {role.mention} участнику {member.mention}", UI_COLOR)
            except Exception as e:
                print(f"Ошибка выдачи автороли: {e}")

    s_roles = get_g_dict(STABLE_ROLES, member.guild.id)
    if str(member.id) in s_roles:
        role = member.guild.get_role(s_roles[str(member.id)])
        if role and role < member.guild.me.top_role:
            try: 
                await member.edit(roles=[role], reason="Sbrole: фиксация при входе")
                return 
            except: 
                pass

    if AUTO_ROLE_ID != 0:
        role = member.guild.get_role(AUTO_ROLE_ID)
        if role:
            try: 
                await member.add_roles(role, reason="Auto-role")
            except: 
                pass

@bot.event
async def on_member_unban(guild, user):
    if user.id in [OWNER_ID, CO_OWNER_ID]: return
    
    g_bans = get_g_dict(TEMP_BANS, guild.id)
    a_bans = get_g_dict(A_TEMP_BANS, guild.id) 

    if str(user.id) in g_bans or str(user.id) in a_bans:
        try: 
            await guild.ban(user, reason="Система: обход темп-бана")
            await send_log(guild, "Защита", f"Снятие бана с <@{user.id}> раньше времени. \nБот вернул бан.", RED_COLOR)
        except: 
            pass

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel is not None:
        bl = get_g_list(BLACKLIST_IDS, member.guild.id)
        if member.id in bl:
            if get_lvl(member.guild.id, member.id) < 3:
                try:
                    await member.move_to(None, reason="Blacklist")
                except: 
                    pass

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    
    bl = get_g_list(BLACKLIST_IDS, message.guild.id)
    if message.author.id in bl:
        if get_lvl(message.guild.id, message.author.id) < 3:
            if not message.content.startswith(f"{bot.command_prefix}unblacklist"):
                try: 
                    await message.delete()
                except: 
                    pass
                return 
    await bot.process_commands(message)

# ==========================================
# СИСТЕМА РОЛЕЙ И ПРОТА 
# ==========================================
async def check_anti_role(guild, member, added_roles):
    wl = get_g_list(WHITELIST_IDS, guild.id)
    actor = await get_audit_actor(guild, discord.AuditLogAction.member_role_update, member.id)
    if actor and actor.id != bot.user.id and actor.id not in wl and actor.id not in [OWNER_ID, CO_OWNER_ID]:
        try: 
            await member.remove_roles(*added_roles, reason="Anti-Role: выдача без прав")
        except: 
            pass

@bot.event
async def on_member_update(before, after):
    if before.roles == after.roles: return
    guild = after.guild

    prota = get_g_list(PROTECTED_USERS, guild.id)
    if after.id in prota:
        missing_roles = [r for r in before.roles if r not in after.roles and r < guild.me.top_role and not r.is_default()]
        if missing_roles:
            try:
                await after.add_roles(*missing_roles, reason="Prota: защита")
            except: 
                pass

    uid_s = str(after.id)
    s_roles = get_g_dict(STABLE_ROLES, guild.id)
    if uid_s in s_roles:
        role_id = s_roles[uid_s]
        current_role_ids = [r.id for r in after.roles]
        expected_role_ids = [guild.id, role_id]

        if set(current_role_ids) != set(expected_role_ids):
            role = guild.get_role(role_id)
            if role and role < guild.me.top_role:
                try: 
                    await after.edit(roles=[role], reason="Sbrole: фиксация")
                except: 
                    pass

    added_roles = [r for r in after.roles if r not in before.roles]
    if added_roles:
        asyncio.create_task(check_anti_role(guild, after, added_roles))

@tasks.loop(seconds=10)
async def check_unbans():
    now = datetime.datetime.now()
    
    # Проходим по всем гильдиям бота
    for guild in bot.guilds:
        gid_str = str(guild.id)
        
        # Проверяем временные баны (pusy)
        temp_bans = get_g_dict(TEMP_BANS, guild.id)
        to_remove = []
        
        for uid, exp in list(temp_bans.items()):
            try: 
                exp_time = datetime.datetime.strptime(exp, "%d.%m.%Y %H:%M:%S")
            except ValueError:
                try: 
                    exp_time = datetime.datetime.strptime(exp, "%d.%m.%Y %H:%M")
                except: 
                    continue
            if now >= exp_time: 
                to_remove.append(uid)
        
        for uid in to_remove:
            if uid in temp_bans:
                del temp_bans[uid]
                try: 
                    await guild.unban(discord.Object(id=int(uid)), reason="Система: срок бана истек")
                    await send_log(guild, "Разбан", f"бан pusy снят с <@{uid}>.", UI_COLOR)
                except: 
                    pass
        
        # Проверяем жесткие баны (apusy)
        hard_bans = get_g_dict(A_TEMP_BANS, guild.id)
        to_remove = []
        
        for uid, exp in list(hard_bans.items()):
            try: 
                exp_time = datetime.datetime.strptime(exp, "%d.%m.%Y %H:%M:%S")
            except ValueError:
                try: 
                    exp_time = datetime.datetime.strptime(exp, "%d.%m.%Y %H:%M")
                except: 
                    continue
            if now >= exp_time: 
                to_remove.append(uid)
        
        for uid in to_remove:
            if uid in hard_bans:
                del hard_bans[uid]
                try: 
                    await guild.unban(discord.Object(id=int(uid)), reason="Система: срок бана истек")
                    await send_log(guild, "Разбан", f"бан apusy снят с <@{uid}>.", UI_COLOR)
                except: 
                    pass

# ==========================================
# --- КОМАНДЫ ---
# ==========================================
@bot.command(name="setlog")
async def setlog_cmd(ctx, channel: discord.TextChannel = None):
    if ctx.author.id not in [OWNER_ID, CO_OWNER_ID]: return
    if not channel: return await reply_err(ctx, "Укажите канал")

    LOG_CHANNELS[str(ctx.guild.id)] = channel.id
    await reply_ok(ctx, f"Канал логов установлен на {channel.mention}")

@bot.command(name="help")
async def help_cmd(ctx):
    lvl = get_lvl(ctx.guild.id, ctx.author.id)

    emb = discord.Embed(title="Справочник команд", color=RED_COLOR)
    emb.add_field(name="[ user ]", value="```\nhelp\nlist\n```", inline=False)

    if lvl >= 1:
        emb.add_field(name="[ low ]", value="```\nblacklist\nunblacklist\n```", inline=False)
    if lvl >= 2:
        emb.add_field(name="[ mid ]", value="```\nclear\npusy\nunpusy\nsbrole\nunsbrole\nunrole\nпрота\nанпрота\n```", inline=False)
    if lvl >= 3:
        lvl3_cmds = "mod\nunmod\nwl_add\nwl_remove\ngiverole\ngiveall\n"
        if ctx.author.id in [OWNER_ID, CO_OWNER_ID]:
            lvl3_cmds += "save_server\nload_server\n"
        emb.add_field(name="[ pusy ]", value=f"```\n{lvl3_cmds}```", inline=False)

    await ctx.send(embed=emb)

@bot.command(name="list")
async def list_cmd(ctx):
    emb = discord.Embed(title=f"{ctx.guild.name}", color=RED_COLOR)

    def safe_fmt(lst):
        if not lst: return "```Пусто```"
        res = "\n".join(lst)
        return res[:1015] + "\n...и другие" if len(res) > 1024 else res

    def get_name(uid):
        return f"<@{uid}>"

    weights = {"pusy": 3, "mid": 2, "low": 1}
    g_access = get_g_dict(USER_ACCESS, ctx.guild.id).copy()

    # Добавляем owner и co_owner как pusy
    if str(OWNER_ID) not in g_access: g_access[str(OWNER_ID)] = "pusy"
    if str(CO_OWNER_ID) not in g_access: g_access[str(CO_OWNER_ID)] = "pusy"

    acc_sorted = sorted(g_access.items(), key=lambda x: weights.get(x[1], 0), reverse=True)

    acc = [f"{get_name(u)} - {l}" for u, l in acc_sorted]
    emb.add_field(name=f"Доступы [{len(acc)}]", value=safe_fmt(acc), inline=False)

    wl = [f"{get_name(u)}" for u in get_g_list(WHITELIST_IDS, ctx.guild.id)]
    emb.add_field(name=f"Вайтлист [{len(wl)}]", value=safe_fmt(wl), inline=False)

    prota = [f"{get_name(u)}" for u in get_g_list(PROTECTED_USERS, ctx.guild.id)]
    emb.add_field(name=f"Прота [{len(prota)}]", value=safe_fmt(prota), inline=False)

    bl = [f"{get_name(u)}" for u in get_g_list(BLACKLIST_IDS, ctx.guild.id)]
    emb.add_field(name=f"Черный список [{len(bl)}]", value=safe_fmt(bl), inline=False)

    combined_bans = get_g_dict(TEMP_BANS, ctx.guild.id).copy()
    combined_bans.update(get_g_dict(A_TEMP_BANS, ctx.guild.id))

    tb = [f"{get_name(u)} (до {exp})" for u, exp in combined_bans.items()]
    emb.add_field(name=f"Временные баны [{len(tb)}]", value=safe_fmt(tb), inline=False)

    await ctx.send(embed=emb)

@bot.command()
async def clear(ctx, amount: int = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 2: return
    if not amount or amount < 1: return await reply_err(ctx, "Укажите количество сообщений")
    if amount > 1000: amount = 1000

    try:
        deleted = await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(f"> **( + )** Удалено **{len(deleted)-1}** сообщений.")
        await send_log(ctx.guild, "Очистка чата", f"{ctx.author.mention} удалил {len(deleted)-1} сообщений в {ctx.channel.mention}.")
        await asyncio.sleep(10)
        try: 
            await msg.delete()
        except: 
            pass
    except discord.Forbidden:
        await reply_err(ctx, "Нет прав на удаление!")
    except Exception as e:
        await reply_err(ctx, f"Ошибка: {e}")

@bot.command()
async def blacklist(ctx, user: discord.User = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 1: return
    if not user: return await reply_err(ctx, "Укажите пользователя")
    if user.id in [OWNER_ID, CO_OWNER_ID]: return await reply_err(ctx, "Нельзя добавить создателя")

    bl = get_g_list(BLACKLIST_IDS, ctx.guild.id)
    if user.id not in bl:
        bl.append(user.id)
        
        member = ctx.guild.get_member(user.id)
        if member and member.voice:
            try: 
                await member.move_to(None, reason="Blacklist")
            except: 
                pass
            
        await reply_ok(ctx, f"{user.mention} добавлен в черный список")
        await send_log(ctx.guild, "ЧС", f"{ctx.author.mention} добавил {user.mention} в ЧС.", RED_COLOR)
    else: 
        await reply_err(ctx, f"{user.mention} уже в черном списке")

@bot.command()
async def unblacklist(ctx, user: discord.User = None):
    if not user: return await reply_err(ctx, "Укажите пользователя")
    is_self_unban = (user.id == ctx.author.id)
    if not is_self_unban and get_lvl(ctx.guild.id, ctx.author.id) < 1: return

    bl = get_g_list(BLACKLIST_IDS, ctx.guild.id)
    if user.id in bl:
        bl.remove(user.id)
        await reply_ok(ctx, f"{user.mention} удален из черного списка")
        await send_log(ctx.guild, "ЧС", f"{ctx.author.mention} вынес {user.mention} из ЧС.")
    else: 
        await reply_err(ctx, "Этого пользователя нет в черном списке")

@bot.command(name="прота")
async def prota_cmd(ctx, user: discord.User = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 2: return
    if not user: return await reply_err(ctx, "Укажите пользователя")

    prota = get_g_list(PROTECTED_USERS, ctx.guild.id)
    if user.id not in prota:
        prota.append(user.id)
        await reply_ok(ctx, f"{user.mention} теперь прота")
        await send_log(ctx.guild, "Прота", f"{ctx.author.mention} выдал проту {user.mention}.")
    else: 
        await reply_err(ctx, f"{user.mention} уже в проте")

@bot.command(name="анпрота")
async def unprota_cmd(ctx, user: discord.User = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 2: return
    if not user: return await reply_err(ctx, "Укажите пользователя")

    prota = get_g_list(PROTECTED_USERS, ctx.guild.id)
    if user.id in prota:
        prota.remove(user.id)
        await reply_ok(ctx, f"{user.mention} убран из проты")
        await send_log(ctx.guild, "Прота", f"{ctx.author.mention} снял проту с {user.mention}.")
    else: 
        await reply_err(ctx, f"{user.mention} не в проте")

@bot.command()
async def pusy(ctx, target: str = None, duration: str = None, *, reason: str = "Не указана"):
    if get_lvl(ctx.guild.id, ctx.author.id) < 2: return
    if not target or not duration:
        return await reply_err(ctx, "Укажите пользователя и время (s, m, h, d).")

    try:
        target_id = int(re.sub(r'[^\d]', '', target))
    except:
        return await reply_err(ctx, "Неверный ID.")
        
    if target_id in [OWNER_ID, CO_OWNER_ID]: 
        return await reply_err(ctx, "Данного пользователя нельзя забанить!")

    match = re.match(r"(\d+)([smhd])", duration.lower())
    if not match: 
        return await reply_err(ctx, "Формат: s, m, h, d.")

    amt = int(match.group(1))
    unit = match.group(2)
    delta = {"d": "days", "h": "hours", "m": "minutes", "s": "seconds"}[unit]
    end = datetime.datetime.now() + datetime.timedelta(**{delta: amt})
    end_str = end.strftime("%d.%m.%Y %H:%M:%S")

    try:
        await ctx.guild.ban(discord.Object(id=target_id), reason=f"pusy бан. Модератор: {ctx.author.name}. Причина: {reason}")
    except discord.Forbidden:
        return await reply_err(ctx, "Нет прав!")
    except Exception:
        pass 
        
    g_bans = get_g_dict(TEMP_BANS, ctx.guild.id)
    g_bans[str(target_id)] = end_str

    time_fmt = end.strftime('%H:%M:%S %d.%m')
    await reply_ok(ctx, f"<@{target_id}> забанен до {time_fmt}")
    await send_log(ctx.guild, "Pusy", f"{ctx.author.mention} забанил <@{target_id}>.\nСрок: до {time_fmt}\nПричина: {reason}", RED_COLOR)

@bot.command()
async def unpusy(ctx, uid: int = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 2: return
    if not uid: return await reply_err(ctx, "Укажите ID")

    a_bans = get_g_dict(A_TEMP_BANS, ctx.guild.id)
    if str(uid) in a_bans:
        return await reply_err(ctx, "Нет прав на снятие этого бана.")

    g_bans = get_g_dict(TEMP_BANS, ctx.guild.id)
    if str(uid) in g_bans: 
        del g_bans[str(uid)]
        
    try: 
        await ctx.guild.unban(discord.Object(id=uid), reason=f"unpusy. Модератор: {ctx.author.name}")
        await reply_ok(ctx, f"бан снят с <@{uid}>")
        await send_log(ctx.guild, "Unpusy", f"{ctx.author.mention} снял pusy бан с <@{uid}>.")
    except: 
        await reply_ok(ctx, f"<@{uid}> удален из базы")

@bot.command(name="apusy")
async def apusy_cmd(ctx, target: str = None, duration: str = None, *, reason: str = "Не указана"):
    if ctx.author.id not in [OWNER_ID, CO_OWNER_ID]: return
    if not target or not duration:
        return await reply_err(ctx, "Укажите пользователя и время (s, m, h, d).")

    try:
        target_id = int(re.sub(r'[^\d]', '', target))
    except:
        return await reply_err(ctx, "Неверный ID.")
        
    if target_id in [OWNER_ID, CO_OWNER_ID]: 
        return await reply_err(ctx, "Данного пользователя нельзя забанить!")

    match = re.match(r"(\d+)([smhd])", duration.lower())
    if not match: 
        return await reply_err(ctx, "Формат: s, m, h, d.")

    amt = int(match.group(1))
    unit = match.group(2)
    delta = {"d": "days", "h": "hours", "m": "minutes", "s": "seconds"}[unit]
    end = datetime.datetime.now() + datetime.timedelta(**{delta: amt})
    end_str = end.strftime("%d.%m.%Y %H:%M:%S")

    try:
        await ctx.guild.ban(discord.Object(id=target_id), reason=f"apusy бан. Выдал: {ctx.author.name}. Причина: {reason}")
    except discord.Forbidden:
        return await reply_err(ctx, "Нет прав!")
    except Exception:
        pass 
        
    a_bans = get_g_dict(A_TEMP_BANS, ctx.guild.id)
    a_bans[str(target_id)] = end_str

    time_fmt = end.strftime('%H:%M:%S %d.%m')
    await reply_ok(ctx, f"<@{target_id}> темпбан до {time_fmt}")
    await send_log(ctx.guild, "Apusy", f"{ctx.author.mention} выдал apusy <@{target_id}>.\nСрок: до {time_fmt}\nПричина: {reason}", RED_COLOR)

@bot.command(name="aunpusy")
async def aunpusy_cmd(ctx, uid: int = None):
    if ctx.author.id not in [OWNER_ID, CO_OWNER_ID]: return
    if not uid: return await reply_err(ctx, "Укажите ID")

    a_bans = get_g_dict(A_TEMP_BANS, ctx.guild.id)
    if str(uid) in a_bans: 
        del a_bans[str(uid)]
        
    try: 
        await ctx.guild.unban(discord.Object(id=uid), reason=f"aunpusy. Снял: {ctx.author.name}")
        await reply_ok(ctx, f"apusy бан снят с <@{uid}>")
        await send_log(ctx.guild, "Aunpusy", f"{ctx.author.mention} снял apusy бан с <@{uid}>.")
    except: 
        await reply_ok(ctx, f"<@{uid}> удален из базы")

@bot.command()
async def sbrole(ctx, user: discord.Member = None, r_id: int = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 2: return
    if not user or not r_id: return await reply_err(ctx, "Укажите пользователя и ID роли")
    
    role = ctx.guild.get_role(r_id)
    if not role: return await reply_err(ctx, "Роль не найдена")

    msg = await reply_info(ctx, "Фиксирую роль...")

    try: 
        await user.edit(roles=[role], reason=f"Sbrole: {ctx.author.name}")
    except discord.Forbidden: 
        return await msg.edit(content="> **( - )** Ошибка прав.")
    except Exception as e: 
        return await msg.edit(content=f"> **( - )** Ошибка: {e}")

    s_roles = get_g_dict(STABLE_ROLES, ctx.guild.id)
    s_roles[str(user.id)] = r_id

    await msg.edit(content=f"> **( + )** Роль **{role.name}** зафиксирована для {user.mention}")
    await send_log(ctx.guild, "Sbrole", f"{ctx.author.mention} зафиксировал роль **{role.name}** для {user.mention}.")

@bot.command()
async def unsbrole(ctx, user: discord.User = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 2: return
    if not user: return await reply_err(ctx, "Укажите пользователя")

    s_roles = get_g_dict(STABLE_ROLES, ctx.guild.id)
    if str(user.id) in s_roles:
        del s_roles[str(user.id)]
        await reply_ok(ctx, f"фиксация снята для {user.mention}")
        await send_log(ctx.guild, "Unsbrole", f"{ctx.author.mention} снял фиксацию с {user.mention}.")
    else: 
        await reply_err(ctx, f"у {user.mention} нет фиксации")

@bot.command()
async def giverole(ctx, user: discord.Member = None, r_id: int = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 3: return
    if not user or not r_id: return await reply_err(ctx, "Укажите пользователя и ID роли")

    role = ctx.guild.get_role(r_id)
    if not role: return await reply_err(ctx, "Роль не найдена")

    try:
        await user.add_roles(role, reason=f"giverole: {ctx.author.name}")
        await reply_ok(ctx, f"роль **{role.name}** выдана {user.mention}")
        await send_log(ctx.guild, "Giverole", f"{ctx.author.mention} выдал роль **{role.name}** {user.mention}.")
    except discord.Forbidden:
        await reply_err(ctx, "Ошибка прав.")
    except Exception as e:
        await reply_err(ctx, f"Ошибка: {e}")

@bot.command()
async def giveall(ctx, r_id: int = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 3: return
    if not r_id: return await reply_err(ctx, "Укажите ID роли")
    
    role = ctx.guild.get_role(r_id)
    if not role: return await reply_err(ctx, "Роль не найдена")

    msg = await reply_info(ctx, f"Выдаю роль **{role.name}**...")

    for m in ctx.guild.members:
        if role not in m.roles:
            try: 
                await m.add_roles(role, reason=f"giveall: {ctx.author.name}")
                await asyncio.sleep(0.05)
            except: 
                continue
            
    await msg.edit(content=f"> **( + )** Роль **{role.name}** выдана всем")
    await send_log(ctx.guild, "Giveall", f"{ctx.author.mention} выдал всем роль **{role.name}**.")

@bot.command()
async def unrole(ctx, user: discord.Member = None, r_id: int = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 2: return
    if not user or not r_id: return await reply_err(ctx, "Укажите пользователя и ID роли")
    
    role = ctx.guild.get_role(r_id)
    if not role: return await reply_err(ctx, "Роль не найдена")
    
    if role in user.roles:
        try:
            await user.remove_roles(role, reason=f"unrole: {ctx.author.name}")
            await reply_ok(ctx, f"роль {role.name} снята у {user.mention}")
            await send_log(ctx.guild, "Unrole", f"{ctx.author.mention} снял роль {role.name} у {user.mention}.")
        except: 
            await reply_err(ctx, "Ошибка прав")

@bot.command()
async def mod(ctx, user: discord.User = None, lvl: str = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 3: return
    if not user or not lvl: return await reply_err(ctx, "Укажите пользователя и уровень (low/mid/pusy)")

    target_lvl = get_lvl(ctx.guild.id, user.id)
    if target_lvl >= 3 and ctx.author.id not in [OWNER_ID, CO_OWNER_ID]:
        return await reply_err(ctx, "Нельзя менять права pusy")

    lvl = lvl.lower()
    if lvl not in ["low", "mid", "pusy"]: 
        return await reply_err(ctx, "Такого уровня нет")

    if ctx.author.id not in [OWNER_ID, CO_OWNER_ID] and lvl != "low": 
        return await reply_err(ctx, "Вы можете выдать только 'low'")

    g_access = get_g_dict(USER_ACCESS, ctx.guild.id)
    g_access[str(user.id)] = lvl
    await reply_ok(ctx, f"{user.mention} выдан доступ **{lvl}**")
    await send_log(ctx.guild, "Mod", f"{ctx.author.mention} выдал доступ **{lvl}** для {user.mention}.")

@bot.command()
async def unmod(ctx, user: discord.User = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 3: return
    if not user: return await reply_err(ctx, "Укажите пользователя")

    target_lvl = get_lvl(ctx.guild.id, user.id)
    if target_lvl >= 3 and ctx.author.id not in [OWNER_ID, CO_OWNER_ID]:
        return await reply_err(ctx, "Нельзя снять доступ у pusy")

    g_access = get_g_dict(USER_ACCESS, ctx.guild.id)
    if str(user.id) in g_access:
        del g_access[str(user.id)]
        await reply_ok(ctx, f"доступ аннулирован для {user.mention}")
        await send_log(ctx.guild, "Unmod", f"{ctx.author.mention} снял доступ у {user.mention}.")
    else:
        await reply_err(ctx, "У пользователя нет доступа")

@bot.command()
async def wl_add(ctx, user: discord.User = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 3: return
    if not user: return await reply_err(ctx, "Укажите пользователя")

    wl = get_g_list(WHITELIST_IDS, ctx.guild.id)
    if int(user.id) not in wl:
        wl.append(int(user.id))
        await reply_ok(ctx, f"{user.mention} добавлен в вайтлист")
        await send_log(ctx.guild, "Вайтлист", f"{ctx.author.mention} добавил {user.mention} в вайтлист.")

@bot.command()
async def wl_remove(ctx, user: discord.User = None):
    if get_lvl(ctx.guild.id, ctx.author.id) < 3: return
    if not user: return await reply_err(ctx, "Укажите пользователя")

    wl = get_g_list(WHITELIST_IDS, ctx.guild.id)
    if int(user.id) in wl:
        wl.remove(int(user.id))
        await reply_ok(ctx, f"{user.mention} удален из вайтлиста")
        await send_log(ctx.guild, "Вайтлист", f"{ctx.author.mention} удалил {user.mention} из вайтлиста.")

@bot.command()
async def say(ctx, *, text: str = None):
    if ctx.author.id not in [OWNER_ID, CO_OWNER_ID]: return
    if not text: return
    try: 
        await ctx.message.delete()
    except: 
        pass
    await ctx.send(text)

# ==========================================
# ИДЕАЛЬНЫЙ БЭКАП: КОПИЯ 1:1 
# ==========================================
def get_overwrites(obj):
    ovrs = {}
    for target, overwrite in obj.overwrites.items():
        if isinstance(target, discord.Role) and not target.managed:
            t_type = "everyone" if target.is_default() else "role"
            ovrs[str(target.id)] = {
                "type": t_type,
                "allow": overwrite.pair()[0].value,
                "deny": overwrite.pair()[1].value
            }
    return ovrs

@bot.command()
async def save_server(ctx, name: str = "default"):
    if ctx.author.id not in [OWNER_ID, CO_OWNER_ID]: return

    msg = await reply_info(ctx, f"Создаю бэкап **{name}**...")

    backup_data = {
        "server_name": ctx.guild.name,
        "server_icon": str(ctx.guild.icon.url) if ctx.guild.icon else None,
        "roles": [], 
        "categories": [], 
        "text_channels": [], 
        "voice_channels": []
    }

    for r in sorted(ctx.guild.roles, key=lambda x: x.position, reverse=True):
        if not r.managed and r.id != ctx.guild.default_role.id:
            backup_data["roles"].append({
                "old_id": str(r.id),
                "name": r.name, 
                "color": r.color.value, 
                "hoist": r.hoist, 
                "mentionable": r.mentionable, 
                "permissions": r.permissions.value,
                "pos": r.position
            })
            
    for c in sorted(ctx.guild.categories, key=lambda x: x.position): 
        backup_data["categories"].append({
            "old_id": str(c.id), 
            "name": c.name, 
            "pos": c.position,
            "overwrites": get_overwrites(c)
        })
        
    for c in sorted(ctx.guild.text_channels, key=lambda x: x.position): 
        backup_data["text_channels"].append({
            "name": c.name, 
            "cat_id": str(c.category.id) if c.category else None, 
            "pos": c.position,
            "topic": c.topic,
            "nsfw": c.is_nsfw(),
            "slowmode": c.slowmode_delay,
            "overwrites": get_overwrites(c)
        })
        
    for c in sorted(ctx.guild.voice_channels, key=lambda x: x.position): 
        backup_data["voice_channels"].append({
            "name": c.name, 
            "cat_id": str(c.category.id) if c.category else None, 
            "pos": c.position,
            "bitrate": c.bitrate,
            "user_limit": c.user_limit,
            "overwrites": get_overwrites(c)
        })
    
    # Сохраняем бэкап в JSON файл
    if save_backup(f"backup_{name}.json", backup_data):
        await msg.edit(content=f"> **( + )** Бэкап **{name}** сохранен")
    else:
        await msg.edit(content=f"> **( - )** Ошибка сохранения бэкапа **{name}**")

@bot.command()
async def list_backups(ctx):
    """Показать список всех бэкапов"""
    if ctx.author.id not in [OWNER_ID, CO_OWNER_ID]: return
    
    import glob
    backups = glob.glob("backup_*.json")
    
    if not backups:
        return await reply_err(ctx, "Нет сохраненных бэкапов")
    
    backup_names = [b.replace("backup_", "").replace(".json", "") for b in backups]
    backup_list = "\n".join([f"• {name}" for name in backup_names])
    
    emb = discord.Embed(title="📦 Список бэкапов", description=backup_list, color=UI_COLOR)
    emb.set_footer(text=f"Всего: {len(backups)} | Использование: .load_server <название>")
    await ctx.send(embed=emb)

@bot.command()
async def load_server(ctx, name: str = "default"):
    if ctx.author.id not in [OWNER_ID, CO_OWNER_ID]: return

    backup = load_data(f"backup_{name}.json", None)
    if not backup: return await reply_err(ctx, f"Бэкап '{name}' не найден")

    msg = await reply_info(ctx, f"Восстанавливаю **{name}**...")

    server_name = backup.get("server_name", ctx.guild.name)
    server_icon_url = backup.get("server_icon")
    icon_bytes = None

    if server_icon_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(server_icon_url) as resp:
                    if resp.status == 200: 
                        icon_bytes = await resp.read()
        except: 
            pass

    try:
        edit_kwargs = {"name": server_name}
        if icon_bytes: edit_kwargs["icon"] = icon_bytes
        await ctx.guild.edit(**edit_kwargs)
        await asyncio.sleep(1)
    except: 
        pass

    for channel in ctx.guild.channels:
        if channel.id != ctx.channel.id:
            try: 
                await channel.delete(reason="Backup: подготовка")
                await asyncio.sleep(0.1)
            except: 
                pass

    for role in ctx.guild.roles:
        if not role.managed and role.id != ctx.guild.default_role.id and role < ctx.guild.me.top_role:
            try: 
                await role.delete(reason="Backup: подготовка")
                await asyncio.sleep(0.1)
            except: 
                pass

    await msg.edit(content="> **( ⏳ )** Воссоздаю роли...")

    role_map = {}       
    category_map = {}   

    def build_overwrites(saved_ovrs):
        new_ovrs = {}
        for t_id_str, data in saved_ovrs.items():
            if data["type"] == "everyone":
                target = ctx.guild.default_role
            else:
                target = role_map.get(t_id_str)
            
            if target:
                new_ovrs[target] = discord.PermissionOverwrite.from_pair(
                    discord.Permissions(data["allow"]),
                    discord.Permissions(data["deny"])
                )
        return new_ovrs

    for r_data in backup.get("roles", []): 
        try:
            new_role = await ctx.guild.create_role(
                name=r_data["name"],
                color=discord.Color(r_data["color"]),
                hoist=r_data["hoist"],
                mentionable=r_data["mentionable"],
                permissions=discord.Permissions(r_data["permissions"]),
                reason="Backup: восстановление"
            )
            role_map[r_data["old_id"]] = new_role
            await asyncio.sleep(0.2)
        except Exception as e: 
            pass

    await msg.edit(content="> **( ⏳ )** Воссоздаю каналы...")

    for cat_data in backup.get("categories", []):
        try: 
            new_cat = await ctx.guild.create_category(
                name=cat_data["name"],
                overwrites=build_overwrites(cat_data.get("overwrites", {})),
                reason="Backup: восстановление"
            )
            category_map[cat_data["old_id"]] = new_cat
            await asyncio.sleep(0.2)
        except Exception as e: 
            pass

    for tc in backup.get("text_channels", []):
        try:
            target_category = category_map.get(tc.get("cat_id")) if tc.get("cat_id") else None
            await ctx.guild.create_text_channel(
                name=tc["name"], 
                category=target_category, 
                topic=tc.get("topic"), 
                nsfw=tc.get("nsfw", False), 
                slowmode_delay=tc.get("slowmode", 0),
                overwrites=build_overwrites(tc.get("overwrites", {})),
                reason="Backup: восстановление"
            )
            await asyncio.sleep(0.2)
        except: 
            pass
        
    for vc in backup.get("voice_channels", []):
        try:
            target_category = category_map.get(vc.get("cat_id")) if vc.get("cat_id") else None
            await ctx.guild.create_voice_channel(
                name=vc["name"], 
                category=target_category, 
                bitrate=vc.get("bitrate", 64000), 
                user_limit=vc.get("user_limit", 0),
                overwrites=build_overwrites(vc.get("overwrites", {})),
                reason="Backup: восстановление"
            )
            await asyncio.sleep(0.2)
        except: 
            pass

    await msg.edit(content=f"> **( + )** Сервер **{server_name}** восстановлен")

@bot.event
async def on_ready():
    if not check_unbans.is_running(): 
        check_unbans.start()
    print(f"Бот запущен как {bot.user}")
    print(f"📊 Подключен к {len(bot.guilds)} серверам")

# ==========================================
# --- FLASK ВЕБ-СЕРВЕР ---
# ==========================================
app = Flask(__name__)
app.secret_key = "lena-syn-imya-ebyrya-materi"
ADMIN_PASSWORD = "pon4ik6662"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error="Неверный пароль")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/api/guilds')
@login_required
def api_guilds():
    guilds = []
    for guild in bot.guilds:
        icon_url = None
        if guild.icon:
            icon_url = f"https://cdn.discordapp.com/icons/{guild.id}/{guild.icon}.png"
        guilds.append({
            'id': str(guild.id),
            'name': guild.name,
            'icon': icon_url,
            'member_count': guild.member_count,
            'owner_id': str(guild.owner_id)
        })
    return jsonify(guilds)

@app.route('/api/guild/<guild_id>/details')
@login_required
def api_guild_details(guild_id):
    """Получить детальную информацию о сервере"""
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return jsonify({'error': 'Guild not found'}), 404
    
    # Подсчет онлайн участников
    online_count = sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot)
    
    # Получение всех ролей с цветами
    roles = []
    for role in sorted(guild.roles, key=lambda x: x.position, reverse=True):
        if not role.is_default():
            roles.append({
                'id': str(role.id),
                'name': role.name,
                'color': f'#{role.color.value:06x}' if role.color.value != 0 else '#99aab5',
                'position': role.position,
                'members': len(role.members)
            })
    
    icon_url = None
    if guild.icon:
        icon_url = f"https://cdn.discordapp.com/icons/{guild.id}/{guild.icon}.png"
    
    banner_url = None
    if guild.banner:
        banner_url = f"https://cdn.discordapp.com/banners/{guild.id}/{guild.banner}.png"
    
    return jsonify({
        'id': str(guild.id),
        'name': guild.name,
        'icon': icon_url,
        'banner': banner_url,
        'member_count': guild.member_count,
        'online_count': online_count,
        'bot_count': sum(1 for m in guild.members if m.bot),
        'text_channels': len(guild.text_channels),
        'voice_channels': len(guild.voice_channels),
        'roles': roles,
        'created_at': guild.created_at.strftime('%d.%m.%Y'),
        'owner_id': str(guild.owner_id),
        'boost_level': guild.premium_tier,
        'boost_count': guild.premium_subscription_count
    })

@app.route('/api/access/<guild_id>')
@login_required
def api_access(guild_id):
    guild_access = get_g_dict(USER_ACCESS, int(guild_id))
    result = []
    for user_id, level in guild_access.items():
        user = bot.get_user(int(user_id))
        avatar_url = None
        if user and user.avatar:
            if isinstance(user.avatar, str):
                avatar_url = f"https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.png"
            else:
                avatar_url = user.avatar.url
        result.append({
            'user_id': user_id,
            'level': level,
            'username': user.name if user else f'User {user_id}',
            'avatar': avatar_url
        })
    return jsonify(result)

@app.route('/api/whitelist/<guild_id>')
@login_required
def api_whitelist(guild_id):
    guild_wl = get_g_list(WHITELIST_IDS, int(guild_id))
    result = []
    for user_id in guild_wl:
        user = bot.get_user(int(user_id))
        avatar_url = None
        if user and user.avatar:
            if isinstance(user.avatar, str):
                avatar_url = f"https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.png"
            else:
                avatar_url = user.avatar.url
        result.append({
            'user_id': str(user_id),
            'username': user.name if user else f'User {user_id}',
            'avatar': avatar_url
        })
    return jsonify(result)

@app.route('/api/blacklist/<guild_id>')
@login_required
def api_blacklist(guild_id):
    guild_bl = get_g_list(BLACKLIST_IDS, int(guild_id))
    result = []
    for user_id in guild_bl:
        user = bot.get_user(int(user_id))
        avatar_url = None
        if user and user.avatar:
            if isinstance(user.avatar, str):
                avatar_url = f"https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.png"
            else:
                avatar_url = user.avatar.url
        result.append({
            'user_id': str(user_id),
            'username': user.name if user else f'User {user_id}',
            'avatar': avatar_url
        })
    return jsonify(result)

@app.route('/api/protected/<guild_id>')
@login_required
def api_protected(guild_id):
    guild_prot = get_g_list(PROTECTED_USERS, int(guild_id))
    result = []
    for user_id in guild_prot:
        user = bot.get_user(int(user_id))
        avatar_url = None
        if user and user.avatar:
            if isinstance(user.avatar, str):
                avatar_url = f"https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.png"
            else:
                avatar_url = user.avatar.url
        result.append({
            'user_id': str(user_id),
            'username': user.name if user else f'User {user_id}',
            'avatar': avatar_url
        })
    return jsonify(result)

@app.route('/api/bans/<guild_id>')
@login_required
def api_bans(guild_id):
    guild_bans = get_g_dict(TEMP_BANS, int(guild_id))
    guild_abans = get_g_dict(A_TEMP_BANS, int(guild_id))
    result = []
    
    for user_id, expire in guild_bans.items():
        user = bot.get_user(int(user_id))
        avatar_url = None
        if user and user.avatar:
            if isinstance(user.avatar, str):
                avatar_url = f"https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.png"
            else:
                avatar_url = user.avatar.url
        result.append({
            'user_id': user_id,
            'username': user.name if user else f'User {user_id}',
            'avatar': avatar_url,
            'expire': expire,
            'type': 'pusy',
            'issued_by': 'Модератор',
            'issued_at': 'N/A'
        })
    
    for user_id, expire in guild_abans.items():
        user = bot.get_user(int(user_id))
        avatar_url = None
        if user and user.avatar:
            if isinstance(user.avatar, str):
                avatar_url = f"https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.png"
            else:
                avatar_url = user.avatar.url
        result.append({
            'user_id': user_id,
            'username': user.name if user else f'User {user_id}',
            'avatar': avatar_url,
            'expire': expire,
            'type': 'apusy',
            'issued_by': 'Администратор',
            'issued_at': 'N/A'
        })
    
    return jsonify(result)

@app.route('/api/members/<guild_id>')
@login_required
def api_members(guild_id):
    """Получить всех участников сервера с полной информацией"""
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return jsonify([])
    
    guild_access = get_g_dict(USER_ACCESS, int(guild_id))
    guild_wl = get_g_list(WHITELIST_IDS, int(guild_id))
    guild_bl = get_g_list(BLACKLIST_IDS, int(guild_id))
    guild_prot = get_g_list(PROTECTED_USERS, int(guild_id))
    guild_bans = get_g_dict(TEMP_BANS, int(guild_id))
    guild_abans = get_g_dict(A_TEMP_BANS, int(guild_id))
    
    result = []
    for member in guild.members:
        if member.bot:
            continue
            
        avatar_url = None
        if member.avatar:
            # Проверяем тип - может быть строка или объект Asset
            if isinstance(member.avatar, str):
                avatar_url = f"https://cdn.discordapp.com/avatars/{member.id}/{member.avatar}.png"
            else:
                avatar_url = member.avatar.url
        
        # Получаем роли с цветами (топ 5)
        roles = []
        for r in sorted(member.roles, key=lambda x: x.position, reverse=True):
            if not r.is_default():
                roles.append({
                    'id': str(r.id),
                    'name': r.name,
                    'color': f'#{r.color.value:06x}' if r.color.value != 0 else '#99aab5'
                })
                if len(roles) >= 5:
                    break
        
        # Проверяем статусы
        access_level = guild_access.get(str(member.id), None)
        is_whitelist = member.id in guild_wl
        is_blacklist = member.id in guild_bl
        is_protected = member.id in guild_prot
        
        ban_info = None
        if str(member.id) in guild_bans:
            ban_info = {'type': 'pusy', 'expire': guild_bans[str(member.id)]}
        elif str(member.id) in guild_abans:
            ban_info = {'type': 'apusy', 'expire': guild_abans[str(member.id)]}
        
        result.append({
            'user_id': str(member.id),
            'username': member.name,
            'display_name': member.display_name,
            'avatar': avatar_url,
            'roles': roles,
            'access_level': access_level,
            'is_whitelist': is_whitelist,
            'is_blacklist': is_blacklist,
            'is_protected': is_protected,
            'ban_info': ban_info,
            'joined_at': member.joined_at.strftime('%d.%m.%Y') if member.joined_at else 'N/A'
        })
    
    return jsonify(result)

@app.route('/api/action', methods=['POST'])
@login_required
def api_action():
    """Выполнить действие (бан, выдача доступа и т.д.)"""
    data = request.json
    action = data.get('action')
    guild_id = int(data.get('guild_id'))
    user_id = data.get('user_id')
    
    guild = bot.get_guild(guild_id)
    if not guild:
        return jsonify({'success': False, 'error': 'Сервер не найден'})
    
    try:
        if action == 'add_access':
            level = data.get('level')
            g_access = get_g_dict(USER_ACCESS, guild_id)
            g_access[str(user_id)] = level
            return jsonify({'success': True, 'message': f'Доступ {level} выдан'})
        
        elif action == 'remove_access':
            g_access = get_g_dict(USER_ACCESS, guild_id)
            if str(user_id) in g_access:
                del g_access[str(user_id)]
            return jsonify({'success': True, 'message': 'Доступ удален'})
        
        elif action == 'add_whitelist':
            wl = get_g_list(WHITELIST_IDS, guild_id)
            if int(user_id) not in wl:
                wl.append(int(user_id))
            return jsonify({'success': True, 'message': 'Добавлен в вайтлист'})
        
        elif action == 'remove_whitelist':
            wl = get_g_list(WHITELIST_IDS, guild_id)
            if int(user_id) in wl:
                wl.remove(int(user_id))
            return jsonify({'success': True, 'message': 'Удален из вайтлиста'})
        
        elif action == 'add_blacklist':
            bl = get_g_list(BLACKLIST_IDS, guild_id)
            if int(user_id) not in bl:
                bl.append(int(user_id))
            return jsonify({'success': True, 'message': 'Добавлен в ЧС'})
        
        elif action == 'remove_blacklist':
            bl = get_g_list(BLACKLIST_IDS, guild_id)
            if int(user_id) in bl:
                bl.remove(int(user_id))
            return jsonify({'success': True, 'message': 'Удален из ЧС'})
        
        elif action == 'add_protected':
            prot = get_g_list(PROTECTED_USERS, guild_id)
            if int(user_id) not in prot:
                prot.append(int(user_id))
            return jsonify({'success': True, 'message': 'Добавлен в проту'})
        
        elif action == 'remove_protected':
            prot = get_g_list(PROTECTED_USERS, guild_id)
            if int(user_id) in prot:
                prot.remove(int(user_id))
            return jsonify({'success': True, 'message': 'Удален из проты'})
        
        elif action == 'ban':
            duration = data.get('duration', '1d')
            ban_type = data.get('ban_type', 'pusy')
            
            match = re.match(r"(\d+)([smhd])", duration.lower())
            if not match:
                return jsonify({'success': False, 'error': 'Неверный формат времени'})
            
            amt = int(match.group(1))
            unit = match.group(2)
            delta = {"d": "days", "h": "hours", "m": "minutes", "s": "seconds"}[unit]
            end = datetime.datetime.now() + datetime.timedelta(**{delta: amt})
            end_str = end.strftime("%d.%m.%Y %H:%M:%S")
            
            member = guild.get_member(int(user_id))
            if member:
                asyncio.run_coroutine_threadsafe(
                    guild.ban(member, reason=f"Веб-панель: {ban_type} бан"),
                    bot.loop
                )
            
            if ban_type == 'apusy':
                g_bans = get_g_dict(A_TEMP_BANS, guild_id)
                g_bans[str(user_id)] = end_str
            else:
                g_bans = get_g_dict(TEMP_BANS, guild_id)
                g_bans[str(user_id)] = end_str
            
            return jsonify({'success': True, 'message': f'Бан выдан до {end_str}'})
        
        elif action == 'unban':
            g_bans = get_g_dict(TEMP_BANS, guild_id)
            g_abans = get_g_dict(A_TEMP_BANS, guild_id)
            
            if str(user_id) in g_bans:
                del g_bans[str(user_id)]
            if str(user_id) in g_abans:
                del g_abans[str(user_id)]
            
            asyncio.run_coroutine_threadsafe(
                guild.unban(discord.Object(id=int(user_id)), reason="Веб-панель: разбан"),
                bot.loop
            )
            return jsonify({'success': True, 'message': 'Бан снят'})
        
        else:
            return jsonify({'success': False, 'error': 'Неизвестное действие'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/autorole/<guild_id>', methods=['GET'])
@login_required
def api_get_autorole(guild_id):
    """Получить настройки автороли для сервера"""
    try:
        auto_roles = get_g_dict(AUTO_ROLES, int(guild_id))
        guild = bot.get_guild(int(guild_id))
        
        result = {
            'enabled': auto_roles.get('enabled', False),
            'role_id': auto_roles.get('role_id', None),
            'role_name': None
        }
        
        if result['role_id'] and guild:
            role = guild.get_role(int(result['role_id']))
            if role:
                result['role_name'] = role.name
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/autorole/<guild_id>', methods=['POST'])
@login_required
def api_set_autorole(guild_id):
    """Установить настройки автороли для сервера"""
    try:
        data = request.json
        enabled = data.get('enabled', False)
        role_id = data.get('role_id', None)
        
        auto_roles = get_g_dict(AUTO_ROLES, int(guild_id))
        auto_roles['enabled'] = enabled
        
        if role_id:
            auto_roles['role_id'] = str(role_id)
        elif not enabled:
            auto_roles['role_id'] = None
        
        
        return jsonify({'success': True, 'message': 'Настройки автороли обновлены'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def run_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Запуск Flask в отдельном потоке
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()
print("🌐 Веб-сервер запущен на http://0.0.0.0:5000")


# ==========================================
# --- ЗАПУСК БОТА ---
# ==========================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    print("ОШИБКА: Токен Discord не найден! Установите переменную окружения DISCORD_TOKEN")
    exit(1)

bot.run(DISCORD_TOKEN)
