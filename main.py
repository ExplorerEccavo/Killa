import discord
from discord import app_commands
from datetime import datetime
import config
import re
import asyncio
import subprocess
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)


class RemoveBlacklistView(discord.ui.View):
    def __init__(self, target_user_id: int, static_ids: list, nicknames: list, reason: str):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id
        self.static_ids = static_ids
        self.nicknames = nicknames
        self.reason = reason

    @discord.ui.button(label="Снять черный список", style=discord.ButtonStyle.danger, custom_id="remove_blacklist")
    async def remove_blacklist(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Проверяем права пользователя
        user_roles = [role.id for role in interaction.user.roles]
        if not any(role_id in config.ALLOWED_ROLES for role_id in user_roles):
            await interaction.response.send_message(
                "❌ У вас недостаточно прав для снятия черного списка!",
                ephemeral=True
            )
            return

        # Формируем упоминания ролей
        mentions = " ".join([
            f"<@&{config.MENTION_ROLES['leader']}>",
            f"<@&{config.MENTION_ROLES['deputy_leader']}>",
            f"<@&{config.MENTION_ROLES['curator_state']}>"
        ])

        # Создаем embed для сообщения о снятии черного списка
        embed_remove = discord.Embed(
            title=config.MESSAGE_CONFIG["title"],
            color=config.MESSAGE_CONFIG["color_remove"],
            timestamp=datetime.now()
        )

        embed_remove.add_field(
            name="Черный список",
            value=f"<t:{int(datetime.now().timestamp())}:F>",
            inline=False
        )

        embed_remove.add_field(
            name="Черный список снят!",
            value=f"<@{self.target_user_id}> ({self.target_user_id})\n\n"
                  f"**Снял:**\n"
                  f"- {interaction.user.mention} ({interaction.user.id} | {interaction.user.name})\n\n"
                  f"**Никнеймы персонажей:**\n"
                  f"{', '.join(self.nicknames) if self.nicknames else 'Не указаны'}\n\n"
                  f"**Статичные айди персонажей:**\n"
                  f"{', '.join(self.static_ids) if self.static_ids else 'Не указаны'}\n\n"
                  f"**Изначальная причина:**\n{self.reason}",
            inline=False
        )

        # Отправляем сообщение о снятии
        await interaction.response.send_message(mentions, embed=embed_remove)

        # Отключаем кнопку в исходном сообщении
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)


def has_allowed_role():
    """Декоратор для проверки прав доступа к команде"""

    async def predicate(interaction: discord.Interaction):
        user_roles = [role.id for role in interaction.user.roles]
        return any(role_id in user_roles for role_id in config.ALLOWED_ROLES)

    return app_commands.check(predicate)


@tree.command(
    name="blacklist",
    description="Добавить пользователя в черный список"
)
@app_commands.describe(
    user="Пользователь Discord",
    static_ids="Статические ID через запятую (1-3 значения)",
    nicknames="Никнеймы через запятую (1-3 значения)",
    reason="Причина блокировки"
)
@has_allowed_role()
async def blacklist(
        interaction: discord.Interaction,
        user: discord.User,
        static_ids: str,
        nicknames: str,
        reason: str
):
    try:
        # Парсинг и валидация аргументов
        static_list = [s.strip() for s in static_ids.split(",") if s.strip()][:3]
        nick_list = [n.strip() for n in nicknames.split(",") if n.strip()][:3]

        if not static_list:
            await interaction.response.send_message(
                "❌ Ошибка: необходимо указать хотя бы один статический ID",
                ephemeral=True
            )
            return

        if not nick_list:
            await interaction.response.send_message(
                "❌ Ошибка: необходимо указать хотя бы один никнейм",
                ephemeral=True
            )
            return

        # Формируем упоминания ролей
        mentions = " ".join([
            f"<@&{config.MENTION_ROLES['leader']}>",
            f"<@&{config.MENTION_ROLES['deputy_leader']}>",
            f"<@&{config.MENTION_ROLES['curator_state']}>"
        ])

        # Создание embed сообщения
        embed = discord.Embed(
            title=config.MESSAGE_CONFIG["title"],
            color=config.MESSAGE_CONFIG["color_blacklist"],
            timestamp=datetime.now()
        )

        embed.add_field(
            name="Черный список",
            value=f"<t:{int(datetime.now().timestamp())}:F>",
            inline=False
        )

        embed.add_field(
            name="Игрок добавлен в черный список!",
            value=f"{user.mention} ({user.id} | {user.name})\n\n"
                  f"**Выдан от:**\n"
                  f"- {interaction.user.mention} ({interaction.user.id} | {interaction.user.name})\n\n"
                  f"**Никнеймы персонажей:**\n"
                  f"{', '.join(nick_list)}\n\n"
                  f"**Статичные айди персонажей:**\n"
                  f"{', '.join(static_list)}\n\n"
                  f"**Причина:**\n{reason}",
            inline=False
        )

        # Создаем View с кнопкой
        view = RemoveBlacklistView(user.id, static_list, nick_list, reason)

        # Отправка в канал черного списка
        channel = bot.get_channel(config.BLACKLIST_CHANNEL_ID)
        if channel:
            await channel.send(mentions, embed=embed, view=view)
            await interaction.response.send_message(
                "✅ Запись успешно добавлена в черный список!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Ошибка: целевой канал не найден",
                ephemeral=True
            )

    except Exception as e:
        await interaction.response.send_message(
            f"❌ Произошла ошибка: {str(e)}",
            ephemeral=True
        )


@blacklist.error
async def blacklist_error(interaction: discord.Interaction, error):
    """Обработчик ошибок для команды blacklist"""
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "❌ У вас недостаточно прав для использования этой команды!",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ Произошла неизвестная ошибка: {str(error)}",
            ephemeral=True
        )


async def update_check():
    try:
        # Fetch latest from origin
        result_fetch = await asyncio.to_thread(subprocess.run, ['git', 'fetch', 'origin'], capture_output=True, text=True)
        if result_fetch.returncode != 0:
            return

        # Check how many commits behind
        result_count = await asyncio.to_thread(subprocess.run, ['git', 'rev-list', '--count', 'HEAD..origin/main'], capture_output=True, text=True)
        if result_count.returncode != 0:
            return

        count = int(result_count.stdout.strip())

        if count > 0:
            # Pull
            result_pull = await asyncio.to_thread(subprocess.run, ['git', 'pull', 'origin', 'main'], capture_output=True, text=True)

    except Exception:
        pass


@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Бот {bot.user} готов к работе!")
    print(f"✅ Команда blacklist зарегистрирована")

    # Setup scheduler for daily updates at midnight
    scheduler = AsyncIOScheduler()
    scheduler.add_job(update_check, CronTrigger(hour=0, minute=0))
    scheduler.start()

    print("Планировщик обновлений запущен. Проверка в 00:00 каждую ночь.")
    await update_check()  # Check for updates at startup


if __name__ == "__main__":
    bot.run(config.BOT_TOKEN)
