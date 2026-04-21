"""Quickest way to generate an avatar - one line!"""

from we_love.avatars import Avatar, avatar

# That's it! One line to generate a unique avatar from any string
Avatar(avatar("hello@world.com")).save_gif("output/quick_start.gif")

print("✨ Created: output/quick_start.gif")
