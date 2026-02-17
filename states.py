"""Telebot-first project.

This repository uses `telebot` (pyTelegramBotAPI). Some legacy aiogram FSM stubs used
to exist in this file; they are intentionally replaced with lightweight constants
so the module stays importable without aiogram.
"""


class UserStates:
    waiting_proof_task_id = "waiting_proof_task_id"


class WithdrawStates:
    choosing_bank = "choosing_bank"
    entering_requisites = "entering_requisites"
    confirming = "confirming"


class AdminAddTaskStates:
    choosing_type = "choosing_type"
    entering_title = "entering_title"
    entering_description = "entering_description"
    entering_reward = "entering_reward"
    entering_comment_text = "entering_comment_text"
