import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
import os
import math
import requests
import re
import random
import asyncio # i hate you
from datetime import datetime, timedelta
# 0x0062FF - blue
ALLOWED_ADMINS = ["1358828167393185906", "1310620656865378355"]  # replace with your user ids (if it is only 1 then do: ["125215150185180"])
api_number = "2757" # change this each time the api link changes (every month), get it in https://discord.gg/ktfhQWysHU

datafile = "data.json" # database for ever user's inventory (using json cuz cant be bothered)
if not os.path.exists(datafile):
    with open(datafile, "w") as f:
        json.dump({}, f)

def load_data():
    with open(datafile, "r") as f:
        return json.load(f)

def save_data(data):
    with open(datafile, "w") as f:
        json.dump(data, f, indent=4)

# formatting values into abbrevations
def format_value(value):
    value = value.upper()
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}
    for suffix, mult in multipliers.items():
        if value.endswith(suffix):
            num = float(value[:-1])
            return f"{num:.1f}{suffix}"
    return value

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"loaded {len(synced)} commands")
    except Exception as e:
        print(f"Error syncing commands: {e}")

#add-pet
@bot.tree.command(name="add-pet", description="Add a pet to a user's inventory")
@app_commands.describe(user="User to add the pet to", pet_name="Name of the pet", amount="How many pets to add")
async def add_pet(interaction: discord.Interaction, user: discord.User, pet_name: str, amount: int = 1):
    if str(interaction.user.id) not in ALLOWED_ADMINS:
        await interaction.response.send_message("You are not allowed to use this command", ephemeral=True)
        return

    if amount < 1:
        await interaction.response.send_message("Amount must be at least 1", ephemeral=True)
        return

    await interaction.response.defer()
    pet_query = pet_name.replace(" ", "+")
    url = f"http://node1.adky.net:{api_number}/api/pet?name={pet_query}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                await interaction.followup.send("Pet not found")
                return
            pet_data = await resp.json()


    pet_value = pet_data.get("value", "").upper()
    if pet_value in ["O/C", "N/A"]: # incase value is not answered or owner's choice
        await interaction.followup.send(f"You can't add this pet because its value is `{pet_value}`")
        return

    user_id = str(user.id)
    data = load_data()
    user_inventory = data.get(user_id, [])
    pet_name_clean = pet_data["name"].title()


    user_inventory.extend([pet_name_clean] * amount)
    data[user_id] = user_inventory
    save_data(data)

    embed = discord.Embed(title=f"Added {amount}x {pet_name_clean}", description=f":white_check_mark: Added**{amount}x {pet_name_clean}** to {user.mention}'s Inventory'", color=0x0062FF)
    await interaction.followup.send(embed=embed)


from typing import Optional

GEM_PACK_VALUES = {
    "10b": 10_000_000_000,
    "1b": 1_000_000_000,
    "100m": 100_000_000,
    "10m": 10_000_000,
    "1m": 1_000_000,
    "100k": 100_000
}

@bot.tree.command(name="add-gems", description="Add gem packs to a user's inventory")
@app_commands.describe(user="User to give gems to", amount="Amount of gem", quantity="How many gem packs to add")
async def add_gems(interaction: discord.Interaction, user: discord.User, amount: str, quantity: int = 1):
    if str(interaction.user.id) not in ALLOWED_ADMINS:
        await interaction.response.send_message("You are not allowed to use this command", ephemeral=True)
        return

    amount_lower = amount.lower()
    if amount_lower not in GEM_PACK_VALUES:
        allowed = ", ".join(GEM_PACK_VALUES.keys())
        await interaction.response.send_message(f"❌ Invalid gem pack, alllowed gem packs: `{allowed}`", ephemeral=True)
        return

    if quantity < 1:
        await interaction.response.send_message("Quantity must be at least 1", ephemeral=True)
        return

    item_name = f"{amount.upper()} Gems"
    total_value = GEM_PACK_VALUES[amount_lower] * quantity

    data = load_data()
    user_id = str(user.id)
    inventory = data.get(user_id, [])
    inventory.extend([item_name] * quantity)
    data[user_id] = inventory
    save_data(data)

    embed = discord.Embed(title=f"Added {quantity}x {item_name}", description=f":white_check_mark: Added **{quantity}x {item_name}** (Total: **{total_value:,}** :gem:) to {user.mention}'s Inventory'", color=0x0062FF)
    await interaction.response.send_message(embed=embed)

@add_gems.autocomplete("amount")
async def gem_pack_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    current = current.lower()
    return [
        app_commands.Choice(name=label.upper(), value=label)
        for label in GEM_PACK_VALUES
        if current in label
    ]

from collections import Counter

class InventoryView(discord.ui.View):
    def __init__(self, user, inventory_items):
        super().__init__(timeout=60)
        self.user = user
        self.page = 0
        self.item_counter = Counter(inventory_items)
        self.items = list(self.item_counter.items())
        self.total_pages = math.ceil(len(self.items) / 15)

    async def fetch_page_embeds(self):
        start = self.page * 15
        end = start + 15
        items_on_page = self.items[start:end]
        description_lines = []

        pet_data_cache = {}

        async with aiohttp.ClientSession() as session:
            for item_name, count in items_on_page:
                if item_name.endswith("Gems"):
                    continue
                if item_name not in pet_data_cache:
                    pet_query = item_name.replace(" ", "+")
                    url = f"http://node1.adky.net:{api_number}/api/pet?name={pet_query}"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            pet_data_cache[item_name] = await resp.json()
                        else:
                            pet_data_cache[item_name] = None

        for item_name, count in items_on_page:
            prefix = f"{count}x " if count > 1 else ""

            if item_name.endswith("Gems"):
                label = item_name.replace(" Gems", "").lower()
                if label in GEM_PACK_VALUES:
                    display = f"{label.upper()} - {label.upper()} 💎"
                else:
                    display = f"{item_name} - Unknown Value"
                description_lines.append(f"- {prefix}{display}")
            else:
                pet_data = pet_data_cache.get(item_name)
                if pet_data:
                    value = format_value(pet_data["value"])
                    display_name = pet_data["name"].title()
                    description_lines.append(f"- {prefix}{display_name} - {value} 💎")
                else:
                    description_lines.append(f"- {prefix}{item_name} - Unknown Value")

        embed = discord.Embed(
            title=f"{self.user.name}'s Inventory",
            description="\n".join(description_lines) or "🪹 Inventory empty",
            color=0x0062FF
        )
        embed.set_footer(text=f"Page {self.page + 1} of {self.total_pages}")
        return embed

    async def update_message(self, interaction):
        embed = await self.fetch_page_embeds()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("Not your inventory", ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("Not your inventory", ephemeral=True)
            return
        if self.page < self.total_pages - 1:
            self.page += 1
            await self.update_message(interaction)


# inventory command
@bot.tree.command(name="inventory", description="Your inventory")
async def inventory(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    data = load_data()
    inventory_items = data.get(user_id, [])
    
    if not inventory_items:
        await interaction.response.send_message(":backpack: Your inventory is **empty**")
        return


    total_value = calculate_total_value(inventory_items)

    view = InventoryView(interaction.user, inventory_items)
    embed = await view.fetch_page_embeds()
    

    embed.set_footer(text=f"{view.page + 1}/{view.total_pages} Page | Total Value: {add_suffix2(total_value)} 💎")
    
    await interaction.response.send_message(embed=embed, view=view)

api_url = f"http://node1.adky.net:{api_number}/api/pet"
def format_pet_name(pet_name):
    return " ".join(word.capitalize() for word in pet_name.split())

def suffix_to_int2(value):
    if value in ["SOON", "N/A"]:
        return value  
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}
    if any(char.isdigit() for char in value):  
        num, suffix = value[:-1], value[-1]
        return float(num) * multipliers.get(suffix, 1) if suffix in multipliers else float(value)
    return value

def add_suffix2(value):
    if isinstance(value, str):  
        return value  
    for suffix, divisor in [("T", 1_000_000_000_000), ("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)]:
        if value >= divisor:
            return f"{round(value / divisor, 2)}{suffix}"
    return str(value)

def get_timestamp(last_updated):
    try:
        match = re.search(r"(\d+)\s*(hour|hours|day|days|week|weeks|month|months)", last_updated.lower())
        if not match:
            return "Unknown"

        num = int(match.group(1))
        unit = match.group(2)

        now = datetime.utcnow()

        if "month" in unit:
            past_date = now - timedelta(days=30 * num)
        elif "week" in unit:
            past_date = now - timedelta(weeks=num)
        elif "day" in unit:
            past_date = now - timedelta(days=num)
        elif "hour" in unit:
            past_date = now - timedelta(hours=num)
        else:
            return "Unknown"

        return int(past_date.timestamp())
    except Exception:
        return "Unknown"


def fetch_pet_details(pet_name):
    formatted_name = format_pet_name(pet_name)
    response = requests.get(api_url, params={"name": formatted_name})

    if response.status_code == 200:
        return response.json()
    return None

@bot.tree.command(name="value", description="Get the value of a pet")
@app_commands.describe(pet_name="Enter the pet's name")
async def pet_value(interaction: discord.Interaction, pet_name: str):
    pet_details = fetch_pet_details(pet_name)

    if pet_details is None:
        await interaction.response.send_message("Pet not found", ephemeral=True)
        return

    deposit_value = suffix_to_int2(pet_details["value"])
    if isinstance(deposit_value, (int, float)):
        depo_value = deposit_value * 0.9  
        formatted_depo_value = add_suffix2(depo_value)
    else:
        formatted_depo_value = deposit_value  

    embed = discord.Embed(
        title=pet_details["name"].title(),  
        color=0x0062FF
    )
    embed.add_field(name="Value", value=pet_details["value"], inline=True)
    embed.add_field(name="Demand", value=pet_details["demand"], inline=True)


    timestamp = get_timestamp(pet_details["last_updated"])
    embed.add_field(name="Last Updated", value=f"<t:{timestamp}:R>", inline=False)
    
    embed.set_thumbnail(url=pet_details["image_url"])
    embed.set_footer(text=f"server name - Credits to Cosmic Values")

    await interaction.response.send_message(embed=embed)

class TipPetView(discord.ui.View):
    def __init__(self, sender: discord.User, receiver: discord.User, pets: list[str]):
        super().__init__(timeout=120)
        self.sender = sender
        self.receiver = receiver
        self.original_pets = pets
        self.pet_map = {i: pet for i, pet in enumerate(pets)}
        self.selected = set()
        self.page = 0
        self.per_page = 9
        self.max_page = math.ceil(len(self.pet_map) / self.per_page)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()

        start = self.page * self.per_page
        end = start + self.per_page
        page_items = list(self.pet_map.items())[start:end]

        for idx, pet_name in page_items:
            selected = idx in self.selected
            style = discord.ButtonStyle.green if selected else discord.ButtonStyle.red
            emoji = "✅" if selected else "❌"
            row = (idx % self.per_page) // 3
            self.add_item(PetButton(label=pet_name, style=style, emoji=emoji, pet_index=idx, row=row))

        self.add_item(NavigationButton("⬅️", -1, row=3))
        self.add_item(SendButton(self.sender, self.receiver, self, row=3))
        self.add_item(NavigationButton("➡️", 1, row=3))

    async def update_view(self, interaction: discord.Interaction):
        self.update_buttons()
        embed = discord.Embed(
            title=f"Send pets to {self.receiver.display_name}",
            description="Click on pets to select/unselect them:",
            color=0x0062FF
        )
        await interaction.response.edit_message(embed=embed, view=self)


class PetButton(discord.ui.Button):
    def __init__(self, label, style, emoji, pet_index, row):
        super().__init__(label=label, style=style, emoji=emoji, row=row)
        self.pet_index = pet_index

    async def callback(self, interaction: discord.Interaction):
        view: TipPetView = self.view
        if interaction.user != view.sender:
            await interaction.response.send_message("Not your command", ephemeral=True)
            return

        if self.pet_index in view.selected:
            view.selected.remove(self.pet_index)
        else:
            view.selected.add(self.pet_index)

        await view.update_view(interaction)


class NavigationButton(discord.ui.Button):
    def __init__(self, emoji, direction, row):
        super().__init__(emoji=emoji, style=discord.ButtonStyle.blurple, row=row)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        view: TipPetView = self.view
        if interaction.user != view.sender:
            await interaction.response.send_message("Not your command", ephemeral=True)
            return

        view.page = (view.page + self.direction) % view.max_page
        await view.update_view(interaction)


class SendButton(discord.ui.Button):
    def __init__(self, sender, receiver, view, row):
        super().__init__(label="Send", style=discord.ButtonStyle.green, row=row)
        self.sender = sender
        self.receiver = receiver
        self.tip_view = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.sender:
            await interaction.response.send_message("Not your command", ephemeral=True)
            return

        if not self.tip_view.selected:
            await interaction.response.send_message("No pets selected to send", ephemeral=True)
            return

        data = load_data()
        sender_id = str(self.sender.id)
        receiver_id = str(self.receiver.id)

        sender_pets = data.get(sender_id, [])
        receiver_pets = data.get(receiver_id, [])

        for index in sorted(self.tip_view.selected, reverse=True):
            receiver_pets.append(sender_pets[index])
            del sender_pets[index]

        data[sender_id] = sender_pets
        data[receiver_id] = receiver_pets
        save_data(data)

        await interaction.response.edit_message(
            content=f"✅ Sent {len(self.tip_view.selected)} item(s) to {self.receiver.mention}",
            embed=None,
            view=None
        )
        self.tip_view.stop()

# tip
@bot.tree.command(name="tip", description="Send your pets to another user")
@app_commands.describe(user="The user to send pets to")
async def tip(interaction: discord.Interaction, user: discord.User):
    if user == interaction.user:
        await interaction.response.send_message("You can't tip yourself", ephemeral=True)
        return

    data = load_data()
    user_id = str(interaction.user.id)
    pets = data.get(user_id, [])

    if not pets:
        await interaction.response.send_message(":backpack: Your inventory is **empty**", ephemeral=True)
        return

    view = TipPetView(interaction.user, user, pets)
    embed = discord.Embed(
        title=f"Send pets to {user.display_name}",
        description="Click on pets to select/unselect them:",
        color=0x0062FF
    )
    await interaction.response.send_message(embed=embed, view=view)

WITHDRAW_CATEGORY_NAME = "Withdraws"
def load_withdraws():
    try:
        with open("withdraws.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_withdraws(data):
    with open("withdraws.json", "w") as f:
        json.dump(data, f, indent=4)

class WithdrawView(discord.ui.View):
    def __init__(self, user: discord.User, inventory_items: list[str]):
        super().__init__(timeout=120)
        self.user = user
        self.original_items = inventory_items
        self.item_map = {i: item for i, item in enumerate(inventory_items)}
        self.selected = set()
        self.page = 0
        self.per_page = 9
        self.max_page = math.ceil(len(self.item_map) / self.per_page)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()

        start = self.page * self.per_page
        end = start + self.per_page
        page_items = list(self.item_map.items())[start:end]

        for idx, item_name in page_items:
            selected = idx in self.selected
            style = discord.ButtonStyle.green if selected else discord.ButtonStyle.red
            emoji = "✅" if selected else "❌"
            row = (idx % self.per_page) // 3
            self.add_item(WithdrawItemButton(label=item_name, style=style, emoji=emoji, item_index=idx, row=row))

        self.add_item(WithdrawAllButton(self.user, self, row=3))
        self.add_item(WithdrawConfirmButton(self.user, self, row=3))
        self.add_item(WithdrawNavigationButton("⬅️", -1, row=3))
        self.add_item(WithdrawNavigationButton("➡️", 1, row=3))

    async def update_view(self, interaction: discord.Interaction):
        self.update_buttons()
        embed = discord.Embed(
            title="Withdraw Pets",
            description="Select the items you want to withdraw.",
            color=0x00ccff
        )
        await interaction.response.edit_message(embed=embed, view=self)

class WithdrawItemButton(discord.ui.Button):
    def __init__(self, label, style, emoji, item_index, row):
        super().__init__(label=label, style=style, emoji=emoji, row=row)
        self.item_index = item_index

    async def callback(self, interaction: discord.Interaction):
        view: WithdrawView = self.view
        if interaction.user != view.user:
            await interaction.response.send_message("This isn't your withdraw menu.", ephemeral=True)
            return

        if self.item_index in view.selected:
            view.selected.remove(self.item_index)
        else:
            view.selected.add(self.item_index)

        await view.update_view(interaction)

class WithdrawNavigationButton(discord.ui.Button):
    def __init__(self, emoji, direction, row):
        super().__init__(emoji=emoji, style=discord.ButtonStyle.blurple, row=row)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        view: WithdrawView = self.view
        if interaction.user != view.user:
            await interaction.response.send_message("This isn't your withdraw menu.", ephemeral=True)
            return

        view.page = (view.page + self.direction) % view.max_page
        await view.update_view(interaction)

class WithdrawConfirmButton(discord.ui.Button):
    def __init__(self, user, view, row):
        super().__init__(label="Withdraw", style=discord.ButtonStyle.green, row=row)
        self.user = user
        self.withdraw_view = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("This isn't your withdraw menu.", ephemeral=True)
            return

        if not self.withdraw_view.selected:
            await interaction.response.send_message("You didn't select any items.", ephemeral=True)
            return

        data = load_data()
        withdraws = load_withdraws()

        user_id = str(self.user.id)
        user_inventory = data.get(user_id, [])

        selected_items = [user_inventory[i] for i in sorted(self.withdraw_view.selected)]

        for index in sorted(self.withdraw_view.selected, reverse=True):
            del user_inventory[index]

        save_data(data)

        withdraws.append({
            "user_id": user_id,
            "user_name": self.user.name,
            "items": selected_items
        })
        save_withdraws(withdraws)

        counts = Counter(selected_items)
        formatted = [f"{count}x {item}" if count > 1 else f"{item}" for item, count in counts.items()]

        category = discord.utils.get(interaction.guild.categories, name=WITHDRAW_CATEGORY_NAME)
        if not category:
            await interaction.response.send_message(f"Category '{WITHDRAW_CATEGORY_NAME}' not found.", ephemeral=True)
            return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }


        staff_role = discord.utils.get(interaction.guild.roles, name="Staff")
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)


        channel = await interaction.guild.create_text_channel(
            name=f"{interaction.user.name}-withdraw",
            category=category,
            overwrites=overwrites)

        await channel.send(
            f"📦 {self.user.mention} has withdrawn:\n" +
            "\n".join(f"- {line}" for line in formatted)
        )

        await interaction.response.edit_message(content=f"✅ Withdrew {len(selected_items)} item(s), check {channel.mention}", embed=None, view=None)
        self.withdraw_view.stop()

class WithdrawAllButton(discord.ui.Button):
    def __init__(self, user, view, row):
        super().__init__(label="Withdraw All", style=discord.ButtonStyle.red, row=row)
        self.user = user
        self.withdraw_view = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("This isn't your withdraw menu.", ephemeral=True)
            return

        data = load_data()
        withdraws = load_withdraws()

        user_id = str(self.user.id)
        user_inventory = data.get(user_id, [])

        if not user_inventory:
            await interaction.response.send_message("Your inventory is already empty. (happens if you use this command twice and try to dupe :clown:)", ephemeral=True)
            return

        selected_items = user_inventory.copy()
        data[user_id] = []
        save_data(data)

        withdraws.append({
            "user_id": user_id,
            "user_name": self.user.name,
            "items": selected_items
        })
        save_withdraws(withdraws)

        counts = Counter(selected_items)
        formatted = [f"{count}x {item}" if count > 1 else f"{item}" for item, count in counts.items()]

        category = discord.utils.get(interaction.guild.categories, name=WITHDRAW_CATEGORY_NAME)
        if not category:
            await interaction.response.send_message(f"Category '{WITHDRAW_CATEGORY_NAME}' not found.", ephemeral=True)
            return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }


        staff_role = discord.utils.get(interaction.guild.roles, name="Staff")
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)


        channel = await interaction.guild.create_text_channel(
            name=f"{interaction.user.name}-withdraw",
            category=category,
            overwrites=overwrites)

        await channel.send(
            f"📦 {self.user.mention} has withdrawn everything:\n" +
            "\n".join(f"- {line}" for line in formatted)
        )

        await interaction.response.edit_message(content=f"✅ Withdrew all items, check {channel.mention}", embed=None, view=None)
        self.withdraw_view.stop()

@bot.tree.command(name="withdraw", description="Withdraw item(s) from your inventory")
async def withdraw(interaction: discord.Interaction):
    data = load_data()
    user_id = str(interaction.user.id)
    inventory_items = data.get(user_id, [])

    if not inventory_items:
        await interaction.response.send_message(":backpack: Your inventory is **empty**", ephemeral=True)
        return

    view = WithdrawView(interaction.user, inventory_items)
    embed = discord.Embed(
        title="Withdraw Pets",
        description="Select the items you want to withdraw",
        color=0x00ccff
    )
    await interaction.response.send_message(embed=embed, view=view)

class QueueView(discord.ui.View):
    def __init__(self, withdraws):
        super().__init__(timeout=120)
        self.withdraws = withdraws
        self.page = 0
        self.per_page = 5
        self.max_page = math.ceil(len(withdraws) / self.per_page)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        self.add_item(QueueNavButton("⬅️", -1))
        self.add_item(QueueNavButton("➡️", 1))

    async def update_view(self, interaction: discord.Interaction):
        self.update_buttons()
        embed = self.generate_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def generate_embed(self):
        embed = discord.Embed(
            title="Withdraw Queue",
            color=0x00ccff
        )

        start = self.page * self.per_page
        end = start + self.per_page
        current = self.withdraws[start:end]

        for w in current:
            counts = Counter(w["items"])
            formatted = [f"{count}x {item}" if count > 1 else f"{item}" for item, count in counts.items()]
            embed.add_field(
                name=w["user_name"],
                value="\n".join(f"- {item}" for item in formatted),
                inline=False
            )

        embed.set_footer(text=f"Page {self.page+1}/{self.max_page}")
        return embed

class QueueNavButton(discord.ui.Button):
    def __init__(self, emoji, direction):
        super().__init__(emoji=emoji, style=discord.ButtonStyle.blurple)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        view: QueueView = self.view
        view.page = (view.page + self.direction) % view.max_page
        await view.update_view(interaction)

@bot.tree.command(name="queue", description="See the withdraw queue")
async def queue(interaction: discord.Interaction):
    withdraws = load_withdraws()

    if not withdraws:
        await interaction.response.send_message("There are no withdraw", ephemeral=True)
        return

    view = QueueView(withdraws)
    embed = view.generate_embed()
    await interaction.response.send_message(embed=embed, view=view)


COINFLIP_CHANNEL_ID = 1365039446860366005  # put your channel ID here

def get_pet_value(pet_name: str) -> int:
    try:
        pet_query = pet_name.replace(" ", "+")
        url = f"http://node1.adky.net:{api_number}/api/pet?name={pet_query}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            value_str = data.get("value", "0").upper()
            if value_str in ["O/C", "N/A"]:
                return 0
            return suffix_to_int2(value_str)
        else:
            return 0
    except Exception as e:
        print(f"Error fetching pet value for {pet_name}: {e}")
        return 0

def get_item_value(item_name: str) -> int:
    if "Gems" in item_name:
        try:
            amount_str = item_name.split()[0].lower()
            return GEM_PACK_VALUES.get(amount_str, 0)
        except:
            return 0
    else:
        return get_pet_value(item_name)

def calculate_total_value(items: list[str]) -> int:
    return sum(get_item_value(item) for item in items)
def summarize_items(items: list[str]) -> list[str]:
    counts = Counter(items)
    return [f"{count}x {item}" if count > 1 else item for item, count in counts.items()]
@bot.tree.command(name="coinflip", description="Start a coinflip ")
async def coinflip(interaction: discord.Interaction):
    data = load_data()
    user_id = str(interaction.user.id)
    inventory_items = data.get(user_id, [])

    if not inventory_items:
        await interaction.response.send_message(":backpack: Your inventory is **empty**", ephemeral=True)
        return

    view = TeamSelectionView(interaction.user)
    embed = discord.Embed(
        title="🎲 Choose Your Color",
        description="Select Red 🔴 or Blue 🔵 to start your coinflip",
        color=0x00ccff
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    await view.wait()

    if not view.team:
        return

    team_view = CoinflipSelectView(interaction.user, inventory_items, view.team)  
    embed = discord.Embed(
        title=f"🎲 Select Items (Choices: {'🔴 Red' if view.team == 'red' else '🔵 Blue'})",
        description="Choose which items to add in your coinflip",
        color=0x00ccff
    )
    await interaction.followup.send(embed=embed, view=team_view, ephemeral=True)

class CoinflipSelectView(discord.ui.View):
    def __init__(self, user: discord.User, inventory_items: list[str], team: str):
        super().__init__(timeout=120)
        self.user = user
        self.inventory_items = inventory_items
        self.team = team 
        self.selected_indices = set()
        self.page = 0
        self.per_page = 9
        self.max_page = max(1, math.ceil(len(inventory_items) / self.per_page))
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        start = self.page * self.per_page
        end = start + self.per_page
        page_items = self.inventory_items[start:end]

        for i, item in enumerate(page_items, start=start):
            selected = i in self.selected_indices
            style = discord.ButtonStyle.green if selected else discord.ButtonStyle.red
            emoji = "✅" if selected else "❌"
            row = (i % self.per_page) // 3
            self.add_item(CoinflipSelectItemButton(
                label=item,
                style=style,
                emoji=emoji,
                idx=i,
                row=row
            ))

        self.add_item(CoinflipSelectConfirmButton(self.user, self, row=3))
        self.add_item(CoinflipSelectNavigationButton("⬅️", -1, row=3))
        self.add_item(CoinflipSelectNavigationButton("➡️", 1, row=3))

    async def update_view(self, interaction: discord.Interaction):
        self.update_buttons()
        embed = discord.Embed(
            title=f"🎲 Select Items (Choices: {'🔴 Red' if self.team == 'red' else '🔵 Blue'})",
            description=f"Selected {len(self.selected_indices)} items\nPage {self.page+1}/{self.max_page}",
            color=0x00ccff
        )
        await interaction.response.edit_message(embed=embed, view=self)

class CoinflipSelectItemButton(discord.ui.Button):
    def __init__(self, label: str, style, emoji, idx, row):
        super().__init__(label=label, style=style, emoji=emoji, row=row)
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        view: CoinflipSelectView = self.view
        if interaction.user != view.user:
            await interaction.response.send_message("This isn't your command.", ephemeral=True)
            return

        if self.idx in view.selected_indices:
            view.selected_indices.remove(self.idx)
        else:
            view.selected_indices.add(self.idx)

        await view.update_view(interaction)

class CoinflipSelectConfirmButton(discord.ui.Button):
    def __init__(self, user, view, row):
        super().__init__(label="Post Coinflip", style=discord.ButtonStyle.green, row=row)
        self.user = user
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("This isn't your comand.", ephemeral=True)
            return

        if not self.view_ref.selected_indices:
            await interaction.response.send_message("Select at least one item.", ephemeral=True)
            return

        data = load_data()
        user_id = str(self.user.id)
        inventory_items = data.get(user_id, [])

        selected_items = [inventory_items[i] for i in sorted(self.view_ref.selected_indices)]
        for idx in sorted(self.view_ref.selected_indices, reverse=True):
            del inventory_items[idx]

        save_data(data)

        channel = interaction.client.get_channel(COINFLIP_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("Coinflip channel not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎲 New {'🔴 Red' if self.view_ref.team == 'red' else '🔵 Blue'} Coinflip",
            description=f"**User:** {self.user.mention}",
            color=0xff0000 if self.view_ref.team == 'red' else 0x0000ff
        )
        embed.add_field(name="Wagered Items", value="\n".join(f"- {item}" for item in summarize_items(selected_items)))
        

        view = CoinflipView(self.user, selected_items, self.view_ref.team)
        message = await channel.send(embed=embed, view=view)
        view.message = message

        await interaction.response.edit_message(
            content="✅ Your coinflip has been sent in the #coinflip channel",
            embed=None,
            view=None
        )
        self.view_ref.stop()


class CoinflipSelectNavigationButton(discord.ui.Button):
    def __init__(self, emoji, direction, row):
        super().__init__(emoji=emoji, style=discord.ButtonStyle.blurple, row=row)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        view: CoinflipSelectView = self.view
        if interaction.user != view.user:
            await interaction.response.send_message("This isn't your command.", ephemeral=True)
            return

        view.page = (view.page + self.direction) % view.max_page
        await view.update_view(interaction)

class TeamSelectionView(discord.ui.View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=30)
        self.user = user
        self.team = None

    @discord.ui.button(label="🔴", style=discord.ButtonStyle.red)
    async def red(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("This isn't your command.", ephemeral=True)
            return
        self.team = 'red'
        await interaction.response.edit_message(content="✅ Selected Red", embed=None, view=None)
        self.stop()

    @discord.ui.button(label="🔵", style=discord.ButtonStyle.blurple)
    async def blue(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("This isn't your command.", ephemeral=True)
            return
        self.team = 'blue'
        await interaction.response.edit_message(content="✅ Selected Blue", embed=None, view=None)
        self.stop()

class CoinflipView(discord.ui.View):
    def __init__(self, starter: discord.User, items: list[str], team: str):
        super().__init__(timeout=300)
        self.starter = starter
        self.items = items
        self.starter_value = calculate_total_value(items)
        self.joiner = None
        self.joiner_items = []
        self.message = None
        self.lock = False
        self.team = team
        self.flipping = False
        self.team_emoji = '🔴' if team == 'red' else '🔵'
        self.team_color = 0xff0000 if team == 'red' else 0x0000ff

    async def update_message(self):
        embed = discord.Embed(
        title=f"{self.team_emoji} {self.starter.display_name}'s Coinflip",
        description=f"Choice: {self.team_emoji}\nValue: {self.starter_value:,} :gem:",
        color=self.team_color
        )
        embed.add_field(
        name="Betted Items",
        value="\n".join(f"- {count}x {item}" for item, count in Counter(self.items).items()),
        inline=False
        )
    
        if self.joiner:
            embed.add_field(
            name=f"{'🔵' if self.team == 'red' else '🔴'} {self.joiner.display_name}'s Wager",
            value="\n".join(f"- {count}x {item}" for item, count in Counter(self.joiner_items).items()),
            inline=False
            )
        else:
            embed.add_field(
            name="Waiting for someone to join",
            value=f"Must bet {int(self.starter_value*0.9):,}-{int(self.starter_value*1.1):,} :gem:",
            inline=False
            )
    
            await self.message.edit(embed=embed, view=self)

    async def on_timeout(self):
        if not self.joiner and self.message:
            data = load_data()
            user_id = str(self.starter.id)
            user_inventory = data.get(user_id, [])
            user_inventory.extend(self.items)
            data[user_id] = user_inventory
            save_data(data)
            try:
                await self.message.delete()
            except:
                pass

    async def animate_flip(self):
        self.flipping = True
        for i in range(5):
            for emoji in ['🔴', '🔵']:
                embed = discord.Embed(
                    title=f"{emoji} Coinflip Rolling {i+1}/5",
                    description=f"{self.team_emoji} VS {'🔴' if self.team == 'blue' else '🔵'}",
                    color=self.team_color if emoji == self.team_emoji else (0xff0000 if emoji == '🔴' else 0x0000ff)
                )
                if self.joiner:
                    embed.add_field(
                        name="Potential Winnings",
                        value="\n".join(f"- {item}" for item in summarize_items(self.items + self.joiner_items)),
                        inline=False
                    )
                try:
                    await self.message.edit(embed=embed)
                except:
                    pass
                await asyncio.sleep(0.5)
        self.flipping = False

    async def resolve_coinflip(self):
        if not self.joiner:
            return

        await self.animate_flip()
        
        winner = random.choice([self.starter, self.joiner])
        all_items = self.items + self.joiner_items
        
        data = load_data()
        winner_id = str(winner.id)
        winner_inventory = data.get(winner_id, [])
        winner_inventory.extend(all_items)
        data[winner_id] = winner_inventory
        save_data(data)
        
        total_value = calculate_total_value(all_items)
        embed = discord.Embed(
            title=f"🎉 {winner.display_name} Won",
            description=f"**Winner:** {winner.mention} \n**Won:** {add_suffix2(total_value)} Value :gem:",
            color=self.team_color
        )
        embed.add_field(
            name="Won Items",
            value="\n".join(f"- {item}" for item in summarize_items(all_items)),
            inline=False
        )
        
        try:
            await self.message.edit(embed=embed, view=None)
        except:
            pass
        self.stop()

    @discord.ui.button(label="✅ Join", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.flipping:
            await interaction.response.send_message("coinflip flipping", ephemeral=True)
            return
        if interaction.user.id == self.starter.id:
            await interaction.response.send_message("Can't join your own coinflip :skull:", ephemeral=True)
            return
        if self.joiner:
            await interaction.response.edit_message(content="Someone has already joined", embed=None, view=None)
            return

        data = load_data()
        user_id = str(interaction.user.id)
        inventory_items = data.get(user_id, [])
        
        if not inventory_items:
            await interaction.response.send_message("Your inventory is **empty**", ephemeral=True)
            return

        view = CoinflipJoinView(interaction.user, inventory_items, self.starter_value)
        embed = discord.Embed(
            title=f"{self.starter.display_name}'s Coinflip",
            description=f"Select items to bet (Requirements: {self.starter_value:,} :gem:)",
            color=self.team_color
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        await view.wait()
        
        if view.confirmed and view.selected_items:
            if self.joiner:  
                await interaction.followup.edit_message(
                    content="❌ Someone has already joined this coinflip.",
                    view=None,
                    message_id=interaction.message.id
                )
                return

            self.lock = True
            self.joiner = interaction.user
            self.joiner_items = view.selected_items

            user_inventory = data.get(user_id, [])
            for item in view.selected_items:
                try:
                    user_inventory.remove(item)
                except ValueError:
                    pass
            data[user_id] = user_inventory
            save_data(data)

            await self.update_message()
            await interaction.followup.send("✅ Joined coinflip successful", ephemeral=True)
            await self.resolve_coinflip()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.starter:
            await interaction.response.send_message("Only the one who made it can cancel", ephemeral=True)
            return

        data = load_data()
        user_id = str(self.starter.id)
        user_inventory = data.get(user_id, [])
        user_inventory.extend(self.items)
        data[user_id] = user_inventory
        save_data(data)

        try:
            await self.message.delete()
        except:
            pass
        await interaction.response.send_message("❌ Coinflip cancelled", ephemeral=True)
        self.stop()

class CoinflipJoinView(discord.ui.View):
    def __init__(self, user: discord.User, inventory_items: list[str], target_value: int):
        super().__init__(timeout=120)
        self.user = user
        self.inventory_items = [(i, item) for i, item in enumerate(inventory_items)]
        self.target_value = target_value
        self.min_value = int(target_value * 0.9)
        self.max_value = int(target_value * 1.1)
        self.selected_positions = set()
        self.current_value = 0
        self.page = 0
        self.per_page = 9
        self.max_page = max(1, math.ceil(len(inventory_items) / self.per_page))
        self.confirmed = False
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        start = self.page * self.per_page
        end = start + self.per_page
        page_items = self.inventory_items[start:end]

        for pos, item_name in page_items:
            selected = pos in self.selected_positions
            style = discord.ButtonStyle.green if selected else discord.ButtonStyle.red
            emoji = "✅" if selected else "❌"
            row = (pos % self.per_page) // 3
            self.add_item(CoinflipJoinItemButton(
                item_name=item_name,
                style=style,
                emoji=emoji,
                position=pos,
                row=row
            ))

        self.add_item(CoinflipJoinConfirmButton(self, row=3))
        self.add_item(CoinflipJoinNavigationButton("⬅️", -1, row=3))
        self.add_item(CoinflipJoinNavigationButton("➡️", 1, row=3))
        
        self.add_item(discord.ui.Button(
            label=f"Value: {self.current_value:,}/{self.min_value:,}-{self.max_value:,}",
            style=discord.ButtonStyle.gray,
            disabled=True,
            row=3
        ))

    async def update_view(self, interaction: discord.Interaction):
        self.update_buttons()
        embed = discord.Embed(
            title="🎲 Select Your Items",
            description=f"Current: {self.current_value:,} :gem:\nRequirement: {self.min_value:,}-{self.max_value:,} :gem:",
            color=0x00ccff
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @property
    def selected_items(self):
        return [self.inventory_items[pos][1] for pos in self.selected_positions]

class CoinflipJoinItemButton(discord.ui.Button):
    def __init__(self, item_name: str, style, emoji, position: int, row: int):
        super().__init__(label=item_name, style=style, emoji=emoji, row=row)
        self.position = position
        self.item_name = item_name

    async def callback(self, interaction: discord.Interaction):
        view: CoinflipJoinView = self.view
        if interaction.user != view.user:
            await interaction.response.send_message("This isn't your command.", ephemeral=True)
            return

        if self.position in view.selected_positions:
            view.selected_positions.remove(self.position)
            view.current_value -= get_item_value(self.item_name)
        else:
            view.selected_positions.add(self.position)
            view.current_value += get_item_value(self.item_name)

        await view.update_view(interaction)

class CoinflipJoinConfirmButton(discord.ui.Button):
    def __init__(self, view, row):
        super().__init__(label="Join", style=discord.ButtonStyle.green, row=row)
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.view_ref.user:
            await interaction.response.send_message("This isn't your command", ephemeral=True)
            return

        if not self.view_ref.selected_positions:
            await interaction.response.send_message("Select at least one item.", ephemeral=True)
            return

        if not (self.view_ref.min_value <= self.view_ref.current_value <= self.view_ref.max_value):
            await interaction.response.send_message(
                f"Your Bet ({self.view_ref.current_value:,}) must be between the worth of "
                f"{self.view_ref.min_value:,} and {self.view_ref.max_value:,} 💎.",
                ephemeral=True
            )
            return

        self.view_ref.confirmed = True
        await interaction.response.edit_message(
            content="✅ Bet confirmed, joining coinflip... :smiling_imp:",
            embed=None,
            view=None
        )
        self.view_ref.stop()

class CoinflipJoinNavigationButton(discord.ui.Button):
    def __init__(self, emoji, direction, row):
        super().__init__(emoji=emoji, style=discord.ButtonStyle.blurple, row=row)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        view: CoinflipJoinView = self.view
        if interaction.user != view.user:
            await interaction.response.send_message("This isn't your command", ephemeral=True)
            return

        view.page = (view.page + self.direction) % view.max_page
        await view.update_view(interaction)

@bot.tree.command(name="deposit", description="Deposit Pets/gems!")
async def deposit(interaction: discord.Interaction):
    user = interaction.user
    guild = interaction.guild


    category = discord.utils.get(guild.categories, name="Deposits")

    if not category:
        category = await guild.create_category("Deposits")


    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }

    staff_role = discord.utils.get(interaction.guild.roles, name="Staff")
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)


    channel = await guild.create_text_channel(
        name=f"deposit-{user.name}",
        category=category,
        overwrites=overwrites
    )

    await interaction.response.send_message(f"✅ Created a deposit ticket: {channel.mention}", ephemeral=True)

    await channel.send(f"{user.mention}, please state the items you'd like to deposit, and wait for staff to assists you.")

bot.run("MTM2MjgxNTIxMjEyOTg4MjM0NA.GH63jf.UzORmvjFBYZ3TawUffH7QmazKGM6hbwYGf45gc")
