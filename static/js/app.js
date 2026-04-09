let guilds = [];
let allMembers = [];

document.addEventListener("DOMContentLoaded", function() {
    loadGuilds();
    loadTheme();
});

function loadTheme() {
    const theme = localStorage.getItem("theme") || "dark";
    document.documentElement.setAttribute("data-theme", theme);
    updateThemeButton(theme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute("data-theme");
    const newTheme = currentTheme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", newTheme);
    localStorage.setItem("theme", newTheme);
    updateThemeButton(newTheme);
}

function updateThemeButton(theme) {
    const btn = document.getElementById("theme-btn");
    btn.textContent = theme === "dark" ? "Светлая тема" : "Темная тема";
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showCopyNotification();
    });
}

function showCopyNotification() {
    const notification = document.getElementById("copy-notification");
    notification.classList.add("show");
    setTimeout(() => {
        notification.classList.remove("show");
    }, 2000);
}

function showTab(tabName) {
    document.querySelectorAll(".tab-content").forEach(content => {
        content.classList.remove("active");
    });
    document.querySelectorAll(".tab").forEach(tab => {
        tab.classList.remove("active");
    });
    
    document.getElementById(tabName + "-content").classList.add("active");
    
    const tabs = document.querySelectorAll(".tab");
    const tabNames = ["guilds", "manage", "autorole", "whitelist", "blacklist", "protected", "bans"];
    tabs.forEach((tab, index) => {
        if (tabNames[index] === tabName) {
            tab.classList.add("active");
        }
    });
    
    if (tabName === "guilds") {
        loadGuilds();
    }
}

async function loadGuilds() {
    const container = document.getElementById("guilds-list");
    container.innerHTML = "<div class=\"loading\">Загрузка серверов...</div>";
    
    try {
        const response = await fetch("/api/guilds");
        guilds = await response.json();
        
        if (guilds.length === 0) {
            container.innerHTML = "<div class=\"empty\">Серверы не найдены</div>";
            return;
        }
        
        container.innerHTML = "<div class=\"guild-grid\"></div>";
        const grid = container.querySelector(".guild-grid");
        
        guilds.forEach(guild => {
            const card = document.createElement("div");
            card.className = "guild-card";
            card.innerHTML = "<div class=\"guild-header\"><img src=\"" + (guild.icon || "https://cdn.discordapp.com/embed/avatars/0.png") + "\" alt=\"" + guild.name + "\" class=\"guild-icon\"><div class=\"guild-info\"><h3>" + guild.name + "</h3><div class=\"guild-stats\">" + guild.member_count + " участников • ID: " + guild.id + "</div></div></div>";
            grid.appendChild(card);
        });
        
        fillGuildSelectors();
    } catch (error) {
        container.innerHTML = "<div class=\"empty\">Ошибка загрузки</div>";
        console.error("Error loading guilds:", error);
    }
}

function fillGuildSelectors() {
    const selectors = ["whitelist-guild", "blacklist-guild", "protected-guild", "bans-guild", "manage-guild", "autorole-guild"];
    
    selectors.forEach(selectorId => {
        const select = document.getElementById(selectorId);
        if (!select) return;
        select.innerHTML = "<option value=\"\">Выберите сервер...</option>";
        guilds.forEach(guild => {
            const option = document.createElement("option");
            option.value = guild.id;
            option.textContent = guild.name;
            select.appendChild(option);
        });
    });
}

async function loadMembers() {
    const guildId = document.getElementById("manage-guild").value;
    const container = document.getElementById("manage-list");
    
    if (!guildId) {
        container.innerHTML = "<div class=\"empty\">Выберите сервер</div>";
        return;
    }
    
    container.innerHTML = "<div class=\"loading\">Загрузка участников...</div>";
    
    try {
        const response = await fetch("/api/members/" + guildId);
        allMembers = await response.json();
        
        if (allMembers.length === 0) {
            container.innerHTML = "<div class=\"empty\">Участники не найдены</div>";
            return;
        }
        
        displayMembers(allMembers);
    } catch (error) {
        container.innerHTML = "<div class=\"empty\">Ошибка загрузки</div>";
        console.error("Error loading members:", error);
    }
}

function displayMembers(members) {
    const container = document.getElementById("manage-list");
    container.innerHTML = "";
    
    members.forEach(member => {
        const card = createMemberCard(member);
        container.appendChild(card);
    });
}

function filterMembers() {
    const search = document.getElementById("member-search").value.toLowerCase();
    const filtered = allMembers.filter(m => 
        m.username.toLowerCase().includes(search) || 
        m.display_name.toLowerCase().includes(search)
    );
    displayMembers(filtered);
}

function createMemberCard(member) {
    const card = document.createElement("div");
    card.className = "member-card";
    
    const guildId = document.getElementById("manage-guild").value;
    
    let rolesHtml = "<div class=\"roles-container\">";
    if (member.roles && member.roles.length > 0) {
        member.roles.forEach(role => {
            rolesHtml += "<span class=\"role-badge\" onclick=\"copyToClipboard('" + role.id + "')\" title=\"Нажмите чтобы скопировать ID: " + role.id + "\">" + role.name + "</span>";
        });
    } else {
        rolesHtml += "<span style=\"color: var(--text-tertiary); font-size: 12px;\">Нет ролей</span>";
    }
    rolesHtml += "</div>";
    
    let statusHtml = "<div class=\"status-container\">";
    let hasStatus = false;
    
    if (member.access_level) {
        const levels = { "low": "Low", "mid": "Mid", "pusy": "Pusy" };
        statusHtml += "<span class=\"status-badge status-access\">" + levels[member.access_level] + "</span>";
        hasStatus = true;
    }
    
    if (member.is_whitelist) {
        statusHtml += "<span class=\"status-badge status-wl\">Whitelist</span>";
        hasStatus = true;
    }
    
    if (member.is_protected) {
        statusHtml += "<span class=\"status-badge status-prot\">Protected</span>";
        hasStatus = true;
    }
    
    if (member.is_blacklist) {
        statusHtml += "<span class=\"status-badge status-bl\">Blacklist</span>";
        hasStatus = true;
    }
    
    if (member.ban_info) {
        statusHtml += "<span class=\"status-badge status-ban\">Banned (" + member.ban_info.type + ")</span>";
        hasStatus = true;
    }
    
    if (!hasStatus) {
        statusHtml += "<span style=\"color: var(--text-tertiary); font-size: 12px;\">Нет специальных статусов</span>";
    }
    
    statusHtml += "</div>";
    
    let actionsHtml = "<div class=\"actions-container\">";
    
    if (!member.access_level) {
        actionsHtml += "<button class=\"action-btn btn-access\" onclick=\"performAction('add_access', '" + guildId + "', '" + member.user_id + "', 'low')\">Low</button>";
        actionsHtml += "<button class=\"action-btn btn-access\" onclick=\"performAction('add_access', '" + guildId + "', '" + member.user_id + "', 'mid')\">Mid</button>";
        actionsHtml += "<button class=\"action-btn btn-access\" onclick=\"performAction('add_access', '" + guildId + "', '" + member.user_id + "', 'pusy')\">Pusy</button>";
    } else {
        actionsHtml += "<button class=\"action-btn btn-remove\" onclick=\"performAction('remove_access', '" + guildId + "', '" + member.user_id + "')\">Забрать доступ</button>";
    }
    
    if (!member.is_whitelist) {
        actionsHtml += "<button class=\"action-btn btn-wl\" onclick=\"performAction('add_whitelist', '" + guildId + "', '" + member.user_id + "')\">Выдать White</button>";
    } else {
        actionsHtml += "<button class=\"action-btn btn-remove\" onclick=\"performAction('remove_whitelist', '" + guildId + "', '" + member.user_id + "')\">Забрать White</button>";
    }
    
    if (!member.is_blacklist) {
        actionsHtml += "<button class=\"action-btn btn-bl\" onclick=\"performAction('add_blacklist', '" + guildId + "', '" + member.user_id + "')\">Выдать Black</button>";
    } else {
        actionsHtml += "<button class=\"action-btn btn-remove\" onclick=\"performAction('remove_blacklist', '" + guildId + "', '" + member.user_id + "')\">Забрать Black</button>";
    }
    
    if (!member.is_protected) {
        actionsHtml += "<button class=\"action-btn btn-prot\" onclick=\"performAction('add_protected', '" + guildId + "', '" + member.user_id + "')\">Выдать Проту</button>";
    } else {
        actionsHtml += "<button class=\"action-btn btn-remove\" onclick=\"performAction('remove_protected', '" + guildId + "', '" + member.user_id + "')\">Снять Проту</button>";
    }
    
    if (!member.ban_info) {
        actionsHtml += "<button class=\"action-btn btn-ban\" onclick=\"banUser('" + guildId + "', '" + member.user_id + "', 'pusy')\">Pusy Ban</button>";
        actionsHtml += "<button class=\"action-btn btn-ban\" style=\"background: #a83232;\" onclick=\"banUser('" + guildId + "', '" + member.user_id + "', 'apusy')\">APusy Ban</button>";
    } else {
        actionsHtml += "<button class=\"action-btn btn-remove\" onclick=\"performAction('unban', '" + guildId + "', '" + member.user_id + "')\">Разбанить</button>";
    }
    
    actionsHtml += "</div>";
    
    let banInfoHtml = "";
    if (member.ban_info) {
        banInfoHtml = "<div style=\"font-size: 12px; color: var(--text-secondary); margin-top: 8px;\">Бан истекает: " + member.ban_info.expire + "</div>";
    }
    
    card.innerHTML = "<div class=\"member-header\"><img src=\"" + (member.avatar || "https://cdn.discordapp.com/embed/avatars/0.png") + "\" alt=\"" + member.username + "\" class=\"member-avatar\"><div class=\"member-info\"><div class=\"member-name\">" + member.display_name + "</div><div class=\"member-id\">@" + member.username + " • " + member.user_id + "</div>" + rolesHtml + statusHtml + banInfoHtml + actionsHtml + "</div></div>";
    
    return card;
}

async function performAction(action, guildId, userId, level) {
    const data = { action: action, guild_id: guildId, user_id: userId };
    if (level) data.level = level;
    
    try {
        const response = await fetch("/api/action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert(result.message);
            loadMembers();
        } else {
            alert("Error: " + result.error);
        }
    } catch (error) {
        alert("Error performing action");
        console.error("Error:", error);
    }
}

function banUser(guildId, userId, banType) {
    const banName = banType === 'apusy' ? 'Жесткий Бан' : 'Временный Бан';
    const duration = prompt("Введите длительность " + banName + " (например: 1h, 30m, 7d):", "1d");
    if (!duration) return;
    
    const data = {
        action: "ban",
        guild_id: guildId,
        user_id: userId,
        duration: duration,
        ban_type: banType
    };
    
    fetch("/api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            alert(result.message);
            loadMembers();
        } else {
            alert("Error: " + result.error);
        }
    })
    .catch(error => {
        alert("Error banning user");
        console.error("Error:", error);
    });
}

async function loadAutoRole() {
    const guildId = document.getElementById("autorole-guild").value;
    const container = document.getElementById("autorole-settings");
    
    if (!guildId) {
        container.innerHTML = "<div class=\"empty\">Выберите сервер</div>";
        return;
    }
    
    container.innerHTML = "<div class=\"loading\">Загрузка...</div>";
    
    try {
        const [settingsResponse, guildResponse] = await Promise.all([
            fetch("/api/autorole/" + guildId),
            fetch("/api/guild/" + guildId + "/details")
        ]);
        
        const settings = await settingsResponse.json();
        const guildDetails = await guildResponse.json();
        
        let rolesOptions = "<option value=\"\">Выберите роль...</option>";
        guildDetails.roles.forEach(role => {
            const selected = settings.role_id == role.id ? "selected" : "";
            rolesOptions += "<option value=\"" + role.id + "\" " + selected + ">" + role.name + "</option>";
        });
        
        container.innerHTML = "<div class=\"autorole-settings-box\"><div class=\"autorole-toggle\"><div class=\"toggle-switch " + (settings.enabled ? "active" : "") + "\" id=\"autorole-toggle\" onclick=\"toggleAutoRole()\"><div class=\"toggle-slider\"></div></div><span style=\"font-size: 16px; font-weight: 600; color: var(--text-primary);\">Включить Автороль</span></div><div class=\"autorole-role-selector\" id=\"role-selector-container\" style=\"display: " + (settings.enabled ? "block" : "none") + ";\"><label>Выберите роль для автоматической выдачи:</label><select id=\"autorole-role-select\">" + rolesOptions + "</select></div><button class=\"autorole-save-btn\" onclick=\"saveAutoRole()\">Сохранить настройки</button><div class=\"autorole-info\">При включении выбранная роль будет автоматически выдаваться всем новым участникам при входе на сервер.</div></div>";
        
    } catch (error) {
        container.innerHTML = "<div class=\"empty\">Ошибка загрузки</div>";
        console.error("Error:", error);
    }
}

function toggleAutoRole() {
    const toggle = document.getElementById("autorole-toggle");
    const roleSelector = document.getElementById("role-selector-container");
    
    toggle.classList.toggle("active");
    
    if (toggle.classList.contains("active")) {
        roleSelector.style.display = "block";
    } else {
        roleSelector.style.display = "none";
    }
}

async function saveAutoRole() {
    const guildId = document.getElementById("autorole-guild").value;
    const toggle = document.getElementById("autorole-toggle");
    const roleSelect = document.getElementById("autorole-role-select");
    
    if (!guildId) {
        alert("Пожалуйста, выберите сервер");
        return;
    }
    
    const enabled = toggle.classList.contains("active");
    const roleId = roleSelect ? roleSelect.value : null;
    
    if (enabled && !roleId) {
        alert("Пожалуйста, выберите роль");
        return;
    }
    
    try {
        const response = await fetch("/api/autorole/" + guildId, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                enabled: enabled,
                role_id: roleId
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert(result.message);
        } else {
            alert("Ошибка: " + result.error);
        }
    } catch (error) {
        alert("Ошибка сохранения настроек");
        console.error("Error:", error);
    }
}

async function loadWhitelist() {
    const guildId = document.getElementById("whitelist-guild").value;
    const container = document.getElementById("whitelist-list");
    
    if (!guildId) {
        container.innerHTML = "<div class=\"empty\">Выберите сервер</div>";
        return;
    }
    
    container.innerHTML = "<div class=\"loading\">Загрузка...</div>";
    
    try {
        const response = await fetch("/api/whitelist/" + guildId);
        const users = await response.json();
        
        if (users.length === 0) {
            container.innerHTML = "<div class=\"empty\">Вайтлист пуст</div>";
            return;
        }
        
        container.innerHTML = "";
        users.forEach(user => {
            const card = createUserCard(user);
            container.appendChild(card);
        });
    } catch (error) {
        container.innerHTML = "<div class=\"empty\">Ошибка загрузки</div>";
        console.error("Error:", error);
    }
}

async function loadBlacklist() {
    const guildId = document.getElementById("blacklist-guild").value;
    const container = document.getElementById("blacklist-list");
    
    if (!guildId) {
        container.innerHTML = "<div class=\"empty\">Выберите сервер</div>";
        return;
    }
    
    container.innerHTML = "<div class=\"loading\">Загрузка...</div>";
    
    try {
        const response = await fetch("/api/blacklist/" + guildId);
        const users = await response.json();
        
        if (users.length === 0) {
            container.innerHTML = "<div class=\"empty\">Черный список пуст</div>";
            return;
        }
        
        container.innerHTML = "";
        users.forEach(user => {
            const card = createUserCard(user);
            container.appendChild(card);
        });
    } catch (error) {
        container.innerHTML = "<div class=\"empty\">Ошибка загрузки</div>";
        console.error("Error:", error);
    }
}

async function loadProtected() {
    const guildId = document.getElementById("protected-guild").value;
    const container = document.getElementById("protected-list");
    
    if (!guildId) {
        container.innerHTML = "<div class=\"empty\">Выберите сервер</div>";
        return;
    }
    
    container.innerHTML = "<div class=\"loading\">Загрузка...</div>";
    
    try {
        const response = await fetch("/api/protected/" + guildId);
        const users = await response.json();
        
        if (users.length === 0) {
            container.innerHTML = "<div class=\"empty\">Нет защищенных пользователей</div>";
            return;
        }
        
        container.innerHTML = "";
        users.forEach(user => {
            const card = createUserCard(user);
            container.appendChild(card);
        });
    } catch (error) {
        container.innerHTML = "<div class=\"empty\">Ошибка загрузки</div>";
        console.error("Error:", error);
    }
}

async function loadBans() {
    const guildId = document.getElementById("bans-guild").value;
    const container = document.getElementById("bans-list");
    
    if (!guildId) {
        container.innerHTML = "<div class=\"empty\">Выберите сервер</div>";
        return;
    }
    
    container.innerHTML = "<div class=\"loading\">Загрузка...</div>";
    
    try {
        const response = await fetch("/api/bans/" + guildId);
        const users = await response.json();
        
        if (users.length === 0) {
            container.innerHTML = "<div class=\"empty\">Нет банов</div>";
            return;
        }
        
        container.innerHTML = "";
        users.forEach(user => {
            const card = createUserCard(user, user.type, user.expire);
            container.appendChild(card);
        });
    } catch (error) {
        container.innerHTML = "<div class=\"empty\">Ошибка загрузки</div>";
        console.error("Error:", error);
    }
}

function createUserCard(user, badge, expire) {
    const card = document.createElement("div");
    card.className = "member-card";
    
    let badgeHtml = "";
    if (badge) {
        const badgeClass = badge === "pusy" || badge === "mid" || badge === "low" ? "badge-" + badge : "badge-ban";
        badgeHtml = "<span class=\"user-badge " + badgeClass + "\">" + badge + "</span>";
    }
    
    let expireHtml = "";
    if (expire) {
        expireHtml = "<div style=\"font-size: 12px; color: var(--text-secondary); margin-top: 4px;\">Истекает: " + expire + "</div>";
    }
    
    let extraInfo = "";
    if (user.issued_by) {
        extraInfo += "<div style=\"font-size: 11px; color: var(--text-tertiary); margin-top: 2px;\">Выдал: " + user.issued_by + "</div>";
    }
    
    card.innerHTML = "<div class=\"member-header\"><img src=\"" + (user.avatar || "https://cdn.discordapp.com/embed/avatars/0.png") + "\" alt=\"" + user.username + "\" class=\"member-avatar\"><div class=\"member-info\"><div class=\"member-name\">" + user.username + "</div><div class=\"member-id\">" + user.user_id + "</div>" + expireHtml + extraInfo + badgeHtml + "</div></div>";
    
    return card;
}
