from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import Config
from database import db
from utils.permissions import is_admin
import logging

log = logging.getLogger("GETO")


@Client.on_chat_join_request()
async def on_join_request(client, request):
    try:
        chat = await db.get_chat(request.chat.id)
        if not chat.get("joinrequest_notify", True):
            return

        user = request.from_user

        # Auto approve check
        if chat.get("auto_approve", False):
            try:
                await client.approve_chat_join_request(request.chat.id, user.id)
                log.info(f"[JR] Auto-approved {user.id} for {request.chat.id}")
            except Exception as e:
                log.error(f"[JR] Auto-approve failed: {e}")
            return

        text = (
            f"📨 <b>New Join Request</b>\n\n"
            f"👤 <b>Name:</b> {user.first_name or ''}\n"
            f"🔗 <b>Username:</b> @{user.username or 'None'}\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"💬 <b>Chat:</b> {request.chat.title}"
        )

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🟢 ACCEPT", callback_data=f"jr_accept:{request.chat.id}:{user.id}"),
                InlineKeyboardButton("🔴 DECLINE", callback_data=f"jr_decline:{request.chat.id}:{user.id}")
            ],
            [
                InlineKeyboardButton("👤 USER INFO", url=f"tg://user?id={user.id}")
            ]
        ])

        try:
            await client.send_message(request.chat.id, text, reply_markup=buttons)
        except Exception as e:
            log.error(f"[JR] Cannot send to group: {e}")
            if Config.LOG_CHANNEL:
                await client.send_message(Config.LOG_CHANNEL, text, reply_markup=buttons)

    except Exception as e:
        log.error(f"[JR] on_join_request error: {e}")


@Client.on_callback_query(filters.regex(r"^jr_(accept|decline):"))
async def jr_action(client, cb):
    # Parse data: "jr_accept:chat_id:user_id" = 3 parts
    try:
        action_full, chat_id, user_id = cb.data.split(":")
        chat_id, user_id = int(chat_id), int(user_id)
        action = action_full.replace("jr_", "")  # "accept" or "decline"
    except Exception as e:
        return await cb.answer(f"❌ Invalid data: {e}", show_alert=True)

    log.info(f"[JR] Action={action}, chat={chat_id}, user={user_id}, by={cb.from_user.id}")

    # Check admin
    try:
        admin_check = await is_admin(client, chat_id, cb.from_user.id)
    except Exception as e:
        return await cb.answer(f"❌ Admin check failed: {e}", show_alert=True)

    if not admin_check:
        return await cb.answer("❌ Admin only.", show_alert=True)

    # Check bot permissions
    try:
        me = await client.get_chat_member(chat_id, "me")
        can_invite = getattr(me.privileges, "can_invite_users", False)
        can_restrict = getattr(me.privileges, "can_restrict_members", False)

        log.info(f"[JR] Bot perms - invite={can_invite}, restrict={can_restrict}")

        if not can_invite:
            return await cb.answer(
                "❌ Bot ko 'Invite Users' permission chahiye!\n"
                "Group → Manage → Bot → Invite Users ON",
                show_alert=True
            )
    except Exception as e:
        log.error(f"[JR] Permission check failed: {e}")

    # Execute action
    try:
        if action == "accept":
            await client.approve_chat_join_request(chat_id, user_id)
            log.info(f"[JR] ✅ Approved {user_id}")
            try:
                await cb.message.edit_text(
                    cb.message.text + f"\n\n✅ <b>Approved by</b> {cb.from_user.mention}"
                )
            except Exception:
                pass
            await cb.answer("✅ Accepted!", show_alert=False)

        else:
            await client.decline_chat_join_request(chat_id, user_id)
            log.info(f"[JR] ❌ Declined {user_id}")
            try:
                await cb.message.edit_text(
                    cb.message.text + f"\n\n❌ <b>Declined by</b> {cb.from_user.mention}"
                )
            except Exception:
                pass
            await cb.answer("❌ Declined!", show_alert=False)

    except Exception as e:
        err = str(e)
        log.error(f"[JR] Action failed: {err}")

        # Friendly error messages
        if "CHAT_ADMIN_REQUIRED" in err or "not enough rights" in err.lower():
            msg = (
                "❌ Bot ke paas permission nahi hai!\n\n"
                "Fix:\n"
                "1. Group → Manage → Administrators\n"
                "2. Bot pe click karo\n"
                "3. 'Invite Users' + 'Ban Users' ON karo\n"
                "4. Save karo"
            )
        elif "HIDE_REQUESTER_MISSING" in err:
            msg = "❌ Request expire ho gayi hai ya user ne already join kar liya."
        elif "USER_ALREADY_PARTICIPANT" in err:
            msg = "ℹ️ User already group mein hai."
        elif "PEER_ID_INVALID" in err:
            msg = "❌ Bot ko group mein add nahi kiya ya chat ID galat hai."
        else:
            msg = f"❌ Error: {err}"

        await cb.answer(msg, show_alert=True)


@Client.on_message(filters.command("joinrequests") & filters.group)
async def jr_toggle(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Admin only.")
    chat = await db.get_chat(message.chat.id)
    state = not chat.get("joinrequest_notify", True)
    await db.set_chat_field(message.chat.id, "joinrequest_notify", state)
    await message.reply_text(f"✅ Join-request notifications: {'ON' if state else 'OFF'}")


@Client.on_message(filters.command("autoapprove") & filters.group)
async def auto_approve(client, message):
    if not await is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("❌ Admin only.")
    chat = await db.get_chat(message.chat.id)
    state = not chat.get("auto_approve", False)
    await db.set_chat_field(message.chat.id, "auto_approve", state)
    await message.reply_text(f"✅ Auto-approve: {'ON' if state else 'OFF'}")
