-- Services
local HttpService = game:GetService("HttpService")

-- Config
local WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_URL_HERE" -- Replace with your Discord webhook URL
local GAME_ID = game.PlaceId

-- Visuals
local FILLED_STAR = "?"
local EMPTY_STAR  = "?"
local RATING_COLORS = {
	[1] = 0xE74C3C, -- red
	[2] = 0xE67E22, -- orange
	[3] = 0xF1C40F, -- yellow
	[4] = 0x2ECC71, -- green
	[5] = 0x1ABC9C, -- teal
}
local DEFAULT_COLOR = 0x3498DB

-- Types
export type FeedbackWebhook = {
	send: (self: FeedbackWebhook, player: Player, feedback: string, rating: number) -> (),
}

-- Module
local FeedbackWebhook: FeedbackWebhook = {} :: any

local function makeStars(n: number): string
	n = math.clamp(math.floor(n or 0), 0, 5)
	return string.rep(FILLED_STAR, n) .. string.rep(EMPTY_STAR, 5 - n)
end

-- Public API
function FeedbackWebhook:send(player: Player, feedback: string, rating: number)
	local userId = player.UserId
	local name = player.Name

	local profileUrl = ("https://www.roblox.com/users/%d/profile"):format(userId)
	local avatarUrl  = ("https://www.roblox.com/headshot-thumbnail/image?userId=%d&width=150&height=150&format=png"):format(userId)

	local r = math.clamp(tonumber(rating) or 0, 0, 5)
	local starRow = makeStars(r)
	local color = RATING_COLORS[r] or DEFAULT_COLOR

	local embed = {
		['embeds'] = { {
			['title'] = "??? New Rating",
			['description'] = string.format("**Player:** [%s](%s)", name, profileUrl),
			['color'] = color,
			['fields'] = {
				{
					['name'] = "? Rating",
					['value'] = string.format("%s  **%d/5**", starRow, r),
					['inline'] = false,
				},
				{
					['name'] = "?? Feedback",
					['value'] = string.format("```%s```", feedback),
					['inline'] = false,
				},
				{
					['name'] = "?? UserId",
					['value'] = tostring(userId),
					['inline'] = true,
				},
				{
					['name'] = "?? PlaceId",
					['value'] = tostring(GAME_ID),
					['inline'] = true,
				},
				{
					['name'] = "?? Server JobId",
					['value'] = game.JobId ~= "" and game.JobId or "N/A",
					['inline'] = false,
				},
			},
			['thumbnail'] = { ['url'] = avatarUrl },
			['footer'] = {
				['text'] = os.date("!%Y-%m-%d %H:%M:%S UTC"),
				['icon_url'] = "https://cdn.discordapp.com/attachments/1315743232969146411/1407038140165787759/ICOMM_2.png?ex=68a4a5e2&is=68a35462&hm=e3827db74ef25472fd5a2fda24bc61ad02b275ba3bd8d59d22e3204338d5e5fe&",
			},
			['timestamp'] = os.date("!%Y-%m-%dT%H:%M:%SZ"),
		} },
		['username'] = "Rating System",
	}

	local json = HttpService:JSONEncode(embed)

	pcall(function()
		HttpService:PostAsync(WEBHOOK_URL, json, Enum.HttpContentType.ApplicationJson)
	end)
end

return FeedbackWebhook
