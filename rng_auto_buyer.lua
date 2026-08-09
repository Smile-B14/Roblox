local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local PathfindingService = game:GetService("PathfindingService")
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")
local HttpService = game:GetService("HttpService")

local Player = Players.LocalPlayer
local ENV = getgenv and getgenv() or _G
local SCRIPT_KEY = "SmileB_RNG_AutoBuyer_FinalDynamic"

if ENV[SCRIPT_KEY] and ENV[SCRIPT_KEY].Cleanup then
    pcall(ENV[SCRIPT_KEY].Cleanup)
    task.wait()
end

local State = {
    Dead = false,
    Running = false,
    LoopRunning = false,
    Minimized = false,
    GUI = nil,
    Connections = {},
}
ENV[SCRIPT_KEY] = State

--==============================================================
-- CONFIG
--==============================================================
local SPIN_POSITION = Vector3.new(-384, -6, 68)
local BUY_POSITION = Vector3.new(-378, -6, 73)
local ARRIVAL_DISTANCE = 4
local ACTIVE_RANGE = 100
local SCAN_INTERVAL = 0.025
local SPIN_RESULT_TIMEOUT = 4
local SPIN_RETRY_GAP = 0.25
local BUY_PROMPT_WAIT = 1.5
local BUY_RETRY_GAP = 0.10
local MAX_BUY_TIME = 5
local DATA_REFRESH_SECONDS = 300
local PARSE_YIELD_EVERY = 35
local MAX_VISIBLE_ROWS = 80
local CONFIG_FILE = "SmileB_RNG_Settings.json"

local Settings = {
    NameFilter = true,
    MoneyFilter = false,
    MinGeneration = 1000000,
    Selected = { ["Los Noobinis"] = true },
    WebhookEnabled = false,
    WebhookURL = "",
    WebhookMention = "",
    AutoRefresh = true,
    WindowX = 20,
    WindowY = 120,
    Minimized = false,
}

local GameData = {
    Animals = {},
    AnimalNames = {},
    Mutations = {},
    MutationNames = {},
    Ready = false,
    Refreshing = false,
    LastRefresh = 0,
}

local function Track(conn)
    State.Connections[#State.Connections + 1] = conn
    return conn
end

--==============================================================
-- SAVE / LOAD
--==============================================================
local function HasFileSupport()
    return typeof(writefile) == "function" and typeof(readfile) == "function" and typeof(isfile) == "function"
end

local function SelectedToArray()
    local out = {}
    for name, enabled in pairs(Settings.Selected) do
        if enabled then out[#out + 1] = name end
    end
    table.sort(out)
    return out
end

local function SaveNow()
    if not HasFileSupport() then return end
    local data = {
        NameFilter = Settings.NameFilter,
        MoneyFilter = Settings.MoneyFilter,
        MinGeneration = Settings.MinGeneration,
        Selected = SelectedToArray(),
        WebhookEnabled = Settings.WebhookEnabled,
        WebhookURL = Settings.WebhookURL,
        WebhookMention = Settings.WebhookMention,
        AutoRefresh = Settings.AutoRefresh,
        WindowX = Settings.WindowX,
        WindowY = Settings.WindowY,
        Minimized = State.Minimized,
    }
    local ok, json = pcall(HttpService.JSONEncode, HttpService, data)
    if ok then pcall(writefile, CONFIG_FILE, json) end
end

local SaveQueued = false
local function QueueSave()
    if SaveQueued then return end
    SaveQueued = true
    task.delay(0.35, function()
        SaveQueued = false
        if not State.Dead then SaveNow() end
    end)
end

local function LoadSaved()
    if not HasFileSupport() or not isfile(CONFIG_FILE) then return end
    local ok, raw = pcall(readfile, CONFIG_FILE)
    if not ok then return end
    local ok2, data = pcall(HttpService.JSONDecode, HttpService, raw)
    if not ok2 or typeof(data) ~= "table" then return end
    if typeof(data.NameFilter) == "boolean" then Settings.NameFilter = data.NameFilter end
    if typeof(data.MoneyFilter) == "boolean" then Settings.MoneyFilter = data.MoneyFilter end
    if typeof(data.MinGeneration) == "number" then Settings.MinGeneration = data.MinGeneration end
    if typeof(data.WebhookEnabled) == "boolean" then Settings.WebhookEnabled = data.WebhookEnabled end
    if typeof(data.WebhookURL) == "string" then Settings.WebhookURL = data.WebhookURL end
    if typeof(data.WebhookMention) == "string" then Settings.WebhookMention = data.WebhookMention end
    if typeof(data.AutoRefresh) == "boolean" then Settings.AutoRefresh = data.AutoRefresh end
    if typeof(data.WindowX) == "number" then Settings.WindowX = data.WindowX end
    if typeof(data.WindowY) == "number" then Settings.WindowY = data.WindowY end
    if typeof(data.Minimized) == "boolean" then Settings.Minimized = data.Minimized end
    if typeof(data.Selected) == "table" then
        Settings.Selected = {}
        for _, name in ipairs(data.Selected) do
            if typeof(name) == "string" then Settings.Selected[name] = true end
        end
    end
end
LoadSaved()

--==============================================================
-- CHARACTER / MACHINE
--==============================================================
local Character, Humanoid, Root
local function LoadCharacter()
    Character = Player.Character or Player.CharacterAdded:Wait()
    Humanoid = Character:FindFirstChildOfClass("Humanoid") or Character:WaitForChild("Humanoid")
    Root = Character:FindFirstChild("HumanoidRootPart") or Character:WaitForChild("HumanoidRootPart")
end
LoadCharacter()

local RNGMachine = workspace:FindFirstChild("RNGMachine")
local PromptFolder = RNGMachine and RNGMachine:FindFirstChild("Prompt")
local SpinPrompt = PromptFolder and PromptFolder:FindFirstChild("RNGMachinePrompt")
if not SpinPrompt then
    warn("[SmileB RNG] RNGMachinePrompt not found")
    return
end

--==============================================================
-- UTILS
--==============================================================
local function FormatMoney(n)
    if n == nil then return "?" end
    local a = math.abs(n)
    if a >= 1e15 then return string.format("%.2fQ", n / 1e15) end
    if a >= 1e12 then return string.format("%.2fT", n / 1e12) end
    if a >= 1e9 then return string.format("%.2fB", n / 1e9) end
    if a >= 1e6 then return string.format("%.2fM", n / 1e6) end
    if a >= 1e3 then return string.format("%.2fK", n / 1e3) end
    return tostring(math.floor(n))
end

local function ParseNumber(text)
    if typeof(text) ~= "string" then return tonumber(text) end
    local s = text
    s = s:gsub(",", "")
    s = s:gsub("%$", "")
    s = s:gsub("%s", "")
    s = string.lower(s)
    local mult = 1
    local suffix = s:sub(-1)
    if suffix == "k" then mult = 1e3; s = s:sub(1, -2)
    elseif suffix == "m" then mult = 1e6; s = s:sub(1, -2)
    elseif suffix == "b" then mult = 1e9; s = s:sub(1, -2)
    elseif suffix == "t" then mult = 1e12; s = s:sub(1, -2)
    elseif suffix == "q" then mult = 1e15; s = s:sub(1, -2) end
    local n = tonumber(s)
    return n and (n * mult) or nil
end

local function FlatDistance(a, b)
    local dx, dz = a.X - b.X, a.Z - b.Z
    return math.sqrt(dx * dx + dz * dz)
end

--==============================================================
-- DYNAMIC DATABASE
--==============================================================
local function DecompileWithTimeout(module, timeout)
    if typeof(decompile) ~= "function" then return nil, "decompile unavailable" end
    local finished, success, result = false, false, nil
    task.spawn(function()
        local ok, value = pcall(decompile, module)
        success, result, finished = ok, value, true
    end)
    local started = os.clock()
    while not finished and not State.Dead and os.clock() - started < timeout do task.wait(0.05) end
    if not finished then return nil, "timeout" end
    if not success then return nil, tostring(result) end
    if typeof(result) ~= "string" then return nil, "bad result" end
    return result
end

local function FindEntryKey(source, displayStart, displayName)
    local prefix = source:sub(math.max(1, displayStart - 450), displayStart - 1)
    local bestPos, bestKey = -1, nil
    for pos, key in prefix:gmatch('()%["([^"]+)"%]%s*=%s*{') do
        if pos > bestPos then bestPos, bestKey = pos, key end
    end
    for pos, key in prefix:gmatch("()([%a_][%w_]*)%s*=%s*{") do
        if pos > bestPos then bestPos, bestKey = pos, key end
    end
    return bestKey or displayName
end

local function ParseAnimals(source)
    local db, names, seen = {}, {}, {}
    local pos, count = 1, 0
    while not State.Dead do
        local s, e, displayName = source:find('DisplayName%s*=%s*"([^"]+)"', pos)
        if not s then break end
        local nextDisplay = source:find('DisplayName%s*=%s*"', e + 1)
        local chunkEnd = nextDisplay and (nextDisplay - 1) or math.min(#source, e + 1600)
        local chunk = source:sub(s, chunkEnd)
        local internalKey = FindEntryKey(source, s, displayName)
        local generation = tonumber(chunk:match("Generation%s*=%s*([%d%.eE%-]+)") or "")
        local price = tonumber(chunk:match("Price%s*=%s*([%d%.eE%-]+)") or "")
        local rarity = chunk:match('Rarity%s*=%s*"([^"]+)"')
        local data = { Name = displayName, InternalKey = internalKey, Generation = generation, Price = price, Rarity = rarity }
        db[displayName] = data
        db[string.lower(displayName)] = data
        if internalKey then
            db[internalKey] = data
            db[string.lower(internalKey)] = data
        end
        if not seen[displayName] then
            seen[displayName] = true
            names[#names + 1] = displayName
        end
        count += 1
        if count % PARSE_YIELD_EVERY == 0 then task.wait() end
        pos = e + 1
    end
    table.sort(names, function(a, b)
        local ga = db[a] and db[a].Generation or 0
        local gb = db[b] and db[b].Generation or 0
        if ga == gb then return a < b end
        return ga > gb
    end)
    return db, names
end

local function NormalizeMutationName(name)
    if name == nil then return "" end
    local s = string.lower(tostring(name))
    s = s:gsub("[^%w]", "")
    return s
end

local function ParseMutations(source)
    local normal = { Key = "Normal", DisplayText = "Normal", Modifier = 0 }
    local db = { Normal = normal, normal = normal }
    local names = { "Normal" }
    local pos, count = 1, 0
    while not State.Dead do
        local s, e, displayText = source:find('DisplayText%s*=%s*"([^"]+)"', pos)
        if not s then break end
        local nextDisplay = source:find('DisplayText%s*=%s*"', e + 1)
        local chunkEnd = nextDisplay and (nextDisplay - 1) or math.min(#source, e + 1300)
        local chunk = source:sub(s, chunkEnd)
        local key = FindEntryKey(source, s, displayText)
        local modifier = tonumber(chunk:match("Modifier%s*=%s*([%d%.eE%-]+)") or "") or 0
        local data = { Key = key, DisplayText = displayText, Modifier = modifier }
        db[key] = data
        db[displayText] = data
        db[NormalizeMutationName(key)] = data
        db[NormalizeMutationName(displayText)] = data
        names[#names + 1] = displayText
        count += 1
        if count % PARSE_YIELD_EVERY == 0 then task.wait() end
        pos = e + 1
    end
    return db, names
end

local RenderDatabase, UpdateDatabaseStatus, UpdateSelectedCount
local function RefreshGameData()
    if GameData.Refreshing then return false end
    GameData.Refreshing = true
    if UpdateDatabaseStatus then UpdateDatabaseStatus("Reading live game data...") end
    local datas = ReplicatedStorage:FindFirstChild("Datas")
    local animalsModule = datas and datas:FindFirstChild("Animals")
    local mutationsModule = datas and datas:FindFirstChild("Mutations")
    local animalsSource = animalsModule and DecompileWithTimeout(animalsModule, 10) or nil
    local mutationsSource = mutationsModule and DecompileWithTimeout(mutationsModule, 10) or nil
    if animalsSource then
        local db, names = ParseAnimals(animalsSource)
        if next(db) then GameData.Animals, GameData.AnimalNames = db, names end
    end
    if mutationsSource then
        local db, names = ParseMutations(mutationsSource)
        if next(db) then GameData.Mutations, GameData.MutationNames = db, names end
    end
    GameData.Ready = #GameData.AnimalNames > 0
    GameData.LastRefresh = os.clock()
    GameData.Refreshing = false
    if UpdateDatabaseStatus then
        UpdateDatabaseStatus(GameData.Ready and ("Ready | " .. #GameData.AnimalNames .. " Brainrots | " .. #GameData.MutationNames .. " mutations") or "Database load failed")
    end
    if UpdateSelectedCount then UpdateSelectedCount() end
    if RenderDatabase then RenderDatabase() end
    return GameData.Ready
end

local function GetAnimalData(name)
    if not name then return nil end
    return GameData.Animals[name] or GameData.Animals[string.lower(name)]
end

local function GetMutationData(name)
    if name == nil then return GameData.Mutations.Normal or GameData.Mutations.normal end
    return GameData.Mutations[name] or GameData.Mutations[NormalizeMutationName(name)] or GameData.Mutations.Normal or GameData.Mutations.normal
end

local function GetEffectiveGeneration(base, mutation)
    if base == nil then return nil end
    local m = GetMutationData(mutation)
    return base * (1 + ((m and m.Modifier) or 0))
end

local function GetMutationMultiplier(mutation)
    local m = GetMutationData(mutation)
    return 1 + ((m and m.Modifier) or 0)
end

local function MatchMutationValue(value)
    if value == nil then return nil end
    local data = GameData.Mutations[NormalizeMutationName(value)]
    if data and data.DisplayText ~= "Normal" then return data.DisplayText end
    return nil
end

local function DetectMutation(model)
    if not model then return "Normal" end
    local descendants = model:GetDescendants()
    local objects = { model }
    local rp = model:FindFirstChild("RootPart")
    if rp then objects[#objects + 1] = rp end
    for _, d in ipairs(descendants) do objects[#objects + 1] = d end
    for _, obj in ipairs(objects) do
        for key, value in pairs(obj:GetAttributes()) do
            local keyStr = tostring(key)
            if string.find(string.lower(keyStr), "mutation", 1, true) then
                local found = MatchMutationValue(value)
                if found then return found end
            end
            if value == true then
                local found = MatchMutationValue(keyStr)
                if found then return found end
            end
            if typeof(value) == "string" then
                local found = MatchMutationValue(value)
                if found then return found end
            end
        end
    end
    for _, d in ipairs(descendants) do
        if d:IsA("StringValue") then
            local found = MatchMutationValue(d.Value)
            if found then return found end
        end
    end
    for _, d in ipairs(descendants) do
        local found = MatchMutationValue(d.Name)
        if found then return found end
    end
    return "Normal"
end

--==============================================================
-- PROMPTS
--==============================================================
local PromptBusy = setmetatable({}, { __mode = "k" })
local function FirePromptOnce(prompt)
    if not prompt or not prompt.Parent or not prompt.Enabled then return false end
    if typeof(fireproximityprompt) ~= "function" then return false end
    if PromptBusy[prompt] then return false end
    PromptBusy[prompt] = true
    local ok = pcall(function()
        -- Do NOT pass HoldDuration here. Solara handles the hold itself.
        fireproximityprompt(prompt)
    end)
    local hold = tonumber(prompt.HoldDuration) or 0
    task.delay(math.max(hold, 0.05) + 0.20, function()
        PromptBusy[prompt] = nil
    end)
    return ok
end

local function GetBuyPrompt(model)
    local root = model and model:FindFirstChild("RootPart")
    local attachment = root and root:FindFirstChild("PromptAttachment")
    return attachment and attachment:FindFirstChildWhichIsA("ProximityPrompt") or nil
end

-- IMPORTANT FIX:
-- Result detection no longer requires PromptAttachment.
-- Inactive cached Brainrots are parked near Y=100000; the active result is physically by the machine.
local function IsDisplayedResult(model)
    if not model or not model.Parent or not model:IsA("Model") then return false end
    local rp = model:FindFirstChild("RootPart")
    if not rp then return false end
    if math.abs(rp.Position.Y) > 1000 then return false end
    return (rp.Position - BUY_POSITION).Magnitude < ACTIVE_RANGE
end

local function GetActiveBrainrot()
    local folder = workspace:FindFirstChild("RNGMachineDisplay")
    if not folder then return nil end
    local best, bestDist = nil, math.huge
    for _, model in ipairs(folder:GetChildren()) do
        if IsDisplayedResult(model) then
            local rp = model:FindFirstChild("RootPart")
            local dist = rp and (rp.Position - BUY_POSITION).Magnitude or math.huge
            if dist < bestDist then best, bestDist = model, dist end
        end
    end
    return best
end

--==============================================================
-- MOVEMENT
--==============================================================
local function DirectMove(position)
    if not Humanoid or not Root then return false end
    Humanoid:MoveTo(position)
    local started = os.clock()
    while State.Running and not State.Dead do
        if not Root or not Root.Parent then return false end
        if FlatDistance(Root.Position, position) <= ARRIVAL_DISTANCE then return true end
        if os.clock() - started > 8 then return false end
        task.wait(0.05)
    end
    return false
end

local function MoveTo(position)
    if not State.Running or State.Dead then return false end
    if not Root or not Root.Parent then LoadCharacter() end
    if FlatDistance(Root.Position, position) <= ARRIVAL_DISTANCE then return true end
    local path = PathfindingService:CreatePath({
        AgentRadius = 2,
        AgentHeight = 5,
        AgentCanJump = true,
        AgentJumpHeight = 7,
        AgentMaxSlope = 45,
    })
    local ok = pcall(function() path:ComputeAsync(Root.Position, position) end)
    if not ok or path.Status ~= Enum.PathStatus.Success then return DirectMove(position) end
    for _, waypoint in ipairs(path:GetWaypoints()) do
        if not State.Running or State.Dead then return false end
        if waypoint.Action == Enum.PathWaypointAction.Jump then Humanoid.Jump = true end
        Humanoid:MoveTo(waypoint.Position)
        local started = os.clock()
        while State.Running and not State.Dead do
            if FlatDistance(Root.Position, waypoint.Position) <= ARRIVAL_DISTANCE then break end
            if os.clock() - started > 3 then Humanoid.Jump = true; break end
            task.wait(0.04)
        end
    end
    return FlatDistance(Root.Position, position) <= ARRIVAL_DISTANCE + 3
end

--==============================================================
-- WEBHOOK
--==============================================================
local function GetRequestFunction()
    if typeof(request) == "function" then return request end
    if typeof(http_request) == "function" then return http_request end
    if typeof(syn) == "table" and typeof(syn.request) == "function" then return syn.request end
    return nil
end

local function SendWebhook(name, data, mutation, actualGeneration, reason)
    if not Settings.WebhookEnabled or Settings.WebhookURL == "" then return end
    local req = GetRequestFunction()
    if not req then return end
    local base = data and data.Generation or nil
    local rarity = data and data.Rarity or "Unknown"
    local mult = GetMutationMultiplier(mutation)
    local url, mention = Settings.WebhookURL, Settings.WebhookMention
    task.spawn(function()
        local description = "**Brainrot:** " .. tostring(name)
            .. "\n**Mutation:** " .. tostring(mutation)
            .. "\n**Rarity:** " .. tostring(rarity)
            .. "\n**Income:** $" .. FormatMoney(actualGeneration) .. "/s"
            .. "\n**Matched by:** " .. tostring(reason)
        if mutation ~= "Normal" then
            description ..= "\n**Base income:** $" .. FormatMoney(base) .. "/s"
                .. "\n**Mutation multiplier:** " .. string.format("%.3gx", mult)
        end
        local payload = { embeds = { { title = "RNG Target Found", description = description } } }
        if mention ~= "" then payload.content = mention end
        local ok, body = pcall(HttpService.JSONEncode, HttpService, payload)
        if not ok then return end
        pcall(req, { Url = url, Method = "POST", Headers = { ["Content-Type"] = "application/json" }, Body = body })
    end)
end

--==============================================================
-- UI
--==============================================================
local GUI = Instance.new("ScreenGui")
GUI.Name = "SmileB_RNG_Final"
GUI.ResetOnSpawn = false
GUI.Parent = Player:WaitForChild("PlayerGui")
State.GUI = GUI

local WINDOW_WIDTH, WINDOW_HEIGHT, MINI_SIZE = 420, 590, 58
local Frame = Instance.new("Frame")
Frame.Size = UDim2.fromOffset(WINDOW_WIDTH, WINDOW_HEIGHT)
Frame.Position = UDim2.fromOffset(Settings.WindowX, Settings.WindowY)
Frame.BackgroundColor3 = Color3.fromRGB(22,22,27)
Frame.BorderSizePixel = 0
Frame.ClipsDescendants = true
Frame.Parent = GUI
local FrameCorner = Instance.new("UICorner")
FrameCorner.CornerRadius = UDim.new(0,12)
FrameCorner.Parent = Frame

local TitleBar = Instance.new("Frame")
TitleBar.Size = UDim2.new(1,0,0,44)
TitleBar.BackgroundTransparency = 1
TitleBar.Parent = Frame
local Title = Instance.new("TextLabel")
Title.Size = UDim2.new(1,-100,1,0)
Title.Position = UDim2.fromOffset(14,0)
Title.BackgroundTransparency = 1
Title.Text = "RNG Auto Buyer"
Title.TextXAlignment = Enum.TextXAlignment.Left
Title.Font = Enum.Font.GothamBold
Title.TextSize = 16
Title.TextColor3 = Color3.new(1,1,1)
Title.Parent = TitleBar
local MinimizeButton = Instance.new("TextButton")
MinimizeButton.Size = UDim2.fromOffset(38,30)
MinimizeButton.Position = UDim2.new(1,-47,0,7)
MinimizeButton.BackgroundColor3 = Color3.fromRGB(42,42,48)
MinimizeButton.BorderSizePixel = 0
MinimizeButton.Text = "−"
MinimizeButton.TextColor3 = Color3.new(1,1,1)
MinimizeButton.TextSize = 20
MinimizeButton.Font = Enum.Font.GothamBold
MinimizeButton.Parent = TitleBar
local mc = Instance.new("UICorner")
mc.CornerRadius = UDim.new(0,8)
mc.Parent = MinimizeButton

local Content = Instance.new("Frame")
Content.Size = UDim2.new(1,-20,1,-54)
Content.Position = UDim2.fromOffset(10,46)
Content.BackgroundTransparency = 1
Content.Parent = Frame

local MiniButton = Instance.new("TextButton")
MiniButton.Size = UDim2.fromScale(1,1)
MiniButton.BackgroundTransparency = 1
MiniButton.Text = "↻"
MiniButton.TextColor3 = Color3.new(1,1,1)
MiniButton.TextSize = 31
MiniButton.Font = Enum.Font.GothamBold
MiniButton.Visible = false
MiniButton.Parent = Frame

local function AttachDrag(handle, allowTap, tapCallback)
    local dragging, startMouse, startFrame, activeInput, moved = false, nil, nil, nil, false
    Track(handle.InputBegan:Connect(function(input)
        if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
            dragging, moved, startMouse, startFrame, activeInput = true, false, input.Position, Frame.Position, input
        end
    end))
    Track(UserInputService.InputChanged:Connect(function(input)
        if not dragging then return end
        if input.UserInputType ~= Enum.UserInputType.MouseMovement and input.UserInputType ~= Enum.UserInputType.Touch then return end
        local delta = input.Position - startMouse
        if delta.Magnitude > 5 then moved = true end
        Frame.Position = UDim2.new(startFrame.X.Scale, startFrame.X.Offset + delta.X, startFrame.Y.Scale, startFrame.Y.Offset + delta.Y)
    end))
    Track(UserInputService.InputEnded:Connect(function(input)
        if not dragging then return end
        if input == activeInput or input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
            dragging = false
            Settings.WindowX, Settings.WindowY = Frame.Position.X.Offset, Frame.Position.Y.Offset
            QueueSave()
            if allowTap and not moved and tapCallback then tapCallback() end
        end
    end))
end
AttachDrag(TitleBar, false, nil)

local Animating = false
local function OpenUI()
    if not State.Minimized or Animating then return end
    Animating, State.Minimized = true, false
    TweenService:Create(MiniButton, TweenInfo.new(0.35, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Rotation = MiniButton.Rotation + 360 }):Play()
    local tw = TweenService:Create(Frame, TweenInfo.new(0.28, Enum.EasingStyle.Quint, Enum.EasingDirection.Out), { Size = UDim2.fromOffset(WINDOW_WIDTH, WINDOW_HEIGHT) })
    TweenService:Create(FrameCorner, TweenInfo.new(0.28), { CornerRadius = UDim.new(0,12) }):Play()
    tw:Play()
    tw.Completed:Wait()
    if not State.Minimized then MiniButton.Visible = false; TitleBar.Visible = true; Content.Visible = true end
    Animating = false
    QueueSave()
end

local function MinimizeUI()
    if State.Minimized or Animating then return end
    Animating, State.Minimized = true, true
    TitleBar.Visible, Content.Visible = false, false
    MiniButton.Visible, MiniButton.Rotation = true, 0
    TweenService:Create(MiniButton, TweenInfo.new(0.4, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Rotation = 360 }):Play()
    local tw = TweenService:Create(Frame, TweenInfo.new(0.28, Enum.EasingStyle.Quint, Enum.EasingDirection.Out), { Size = UDim2.fromOffset(MINI_SIZE, MINI_SIZE) })
    TweenService:Create(FrameCorner, TweenInfo.new(0.28), { CornerRadius = UDim.new(1,0) }):Play()
    tw:Play()
    tw.Completed:Wait()
    Animating = false
    QueueSave()
end
Track(MinimizeButton.MouseButton1Click:Connect(MinimizeUI))
AttachDrag(MiniButton, true, OpenUI)

local DatabaseStatus = Instance.new("TextLabel")
DatabaseStatus.Size = UDim2.new(1,0,0,20)
DatabaseStatus.BackgroundTransparency = 1
DatabaseStatus.Text = "Loading current game database..."
DatabaseStatus.TextColor3 = Color3.fromRGB(165,165,175)
DatabaseStatus.TextXAlignment = Enum.TextXAlignment.Left
DatabaseStatus.Font = Enum.Font.Gotham
DatabaseStatus.TextSize = 10
DatabaseStatus.Parent = Content
UpdateDatabaseStatus = function(text) if DatabaseStatus.Parent then DatabaseStatus.Text = text end end

local Status = Instance.new("TextLabel")
Status.Size = UDim2.new(1,0,0,22)
Status.Position = UDim2.fromOffset(0,21)
Status.BackgroundTransparency = 1
Status.Text = "Ready"
Status.TextColor3 = Color3.fromRGB(190,190,195)
Status.TextXAlignment = Enum.TextXAlignment.Left
Status.Font = Enum.Font.Gotham
Status.TextSize = 11
Status.Parent = Content
local function SetStatus(text) if Status.Parent then Status.Text = text end end

local ResultLabel = Instance.new("TextLabel")
ResultLabel.Size = UDim2.new(1,0,0,48)
ResultLabel.Position = UDim2.fromOffset(0,43)
ResultLabel.BackgroundTransparency = 1
ResultLabel.Text = "Spins: 0\nNo result yet"
ResultLabel.TextColor3 = Color3.new(1,1,1)
ResultLabel.TextXAlignment = Enum.TextXAlignment.Left
ResultLabel.TextYAlignment = Enum.TextYAlignment.Top
ResultLabel.Font = Enum.Font.Gotham
ResultLabel.TextSize = 11
ResultLabel.TextWrapped = true
ResultLabel.Parent = Content

local function CreateToggle(text, position, size, getter, setter)
    local b = Instance.new("TextButton")
    b.Size, b.Position, b.BorderSizePixel = size, position, 0
    b.TextColor3, b.Font, b.TextSize = Color3.new(1,1,1), Enum.Font.GothamBold, 10
    b.Parent = Content
    local c = Instance.new("UICorner")
    c.CornerRadius = UDim.new(0,8)
    c.Parent = b
    local function refresh()
        local on = getter()
        b.Text = text .. ": " .. (on and "ON" or "OFF")
        b.BackgroundColor3 = on and Color3.fromRGB(45,145,75) or Color3.fromRGB(72,72,80)
    end
    Track(b.MouseButton1Click:Connect(function()
        setter(not getter())
        refresh()
        QueueSave()
    end))
    refresh()
    return b
end

CreateToggle("NAME", UDim2.fromOffset(0,96), UDim2.fromOffset(125,32), function() return Settings.NameFilter end, function(v) Settings.NameFilter = v end)
CreateToggle("MONEY", UDim2.fromOffset(133,96), UDim2.fromOffset(125,32), function() return Settings.MoneyFilter end, function(v) Settings.MoneyFilter = v end)
CreateToggle("AUTO DATA", UDim2.fromOffset(266,96), UDim2.new(1,-266,0,32), function() return Settings.AutoRefresh end, function(v) Settings.AutoRefresh = v end)

local MoneyInput = Instance.new("TextBox")
MoneyInput.Size = UDim2.new(1,0,0,34)
MoneyInput.Position = UDim2.fromOffset(0,135)
MoneyInput.BackgroundColor3 = Color3.fromRGB(35,35,42)
MoneyInput.BorderSizePixel = 0
MoneyInput.TextColor3 = Color3.new(1,1,1)
MoneyInput.PlaceholderText = "Minimum final income >=  e.g. 10M"
MoneyInput.Text = tostring(Settings.MinGeneration)
MoneyInput.ClearTextOnFocus = false
MoneyInput.Font = Enum.Font.Gotham
MoneyInput.TextSize = 11
MoneyInput.Parent = Content
local mic = Instance.new("UICorner")
mic.CornerRadius = UDim.new(0,8)
mic.Parent = MoneyInput

local function ApplyMoneyInput()
    local value = ParseNumber(MoneyInput.Text)
    if value then
        Settings.MinGeneration = value
        MoneyInput.Text = tostring(value)
        QueueSave()
    else
        MoneyInput.Text = tostring(Settings.MinGeneration)
    end
end
Track(MoneyInput.FocusLost:Connect(ApplyMoneyInput))

local SearchBox = Instance.new("TextBox")
SearchBox.Size = UDim2.new(1,-100,0,32)
SearchBox.Position = UDim2.fromOffset(0,177)
SearchBox.BackgroundColor3 = Color3.fromRGB(35,35,42)
SearchBox.BorderSizePixel = 0
SearchBox.PlaceholderText = "Search Brainrot database..."
SearchBox.Text = ""
SearchBox.TextColor3 = Color3.new(1,1,1)
SearchBox.Font = Enum.Font.Gotham
SearchBox.TextSize = 11
SearchBox.Parent = Content
local sc = Instance.new("UICorner")
sc.CornerRadius = UDim.new(0,8)
sc.Parent = SearchBox

local ClearButton = Instance.new("TextButton")
ClearButton.Size = UDim2.fromOffset(92,32)
ClearButton.Position = UDim2.new(1,-92,0,177)
ClearButton.BackgroundColor3 = Color3.fromRGB(65,65,73)
ClearButton.BorderSizePixel = 0
ClearButton.Text = "CLEAR"
ClearButton.TextColor3 = Color3.new(1,1,1)
ClearButton.Font = Enum.Font.GothamBold
ClearButton.TextSize = 10
ClearButton.Parent = Content
local cc = Instance.new("UICorner")
cc.CornerRadius = UDim.new(0,8)
cc.Parent = ClearButton

local SelectedLabel = Instance.new("TextLabel")
SelectedLabel.Size = UDim2.new(1,0,0,18)
SelectedLabel.Position = UDim2.fromOffset(0,211)
SelectedLabel.BackgroundTransparency = 1
SelectedLabel.TextColor3 = Color3.fromRGB(170,170,180)
SelectedLabel.TextXAlignment = Enum.TextXAlignment.Left
SelectedLabel.Font = Enum.Font.Gotham
SelectedLabel.TextSize = 10
SelectedLabel.Parent = Content

local function CountSelected()
    local n = 0
    for _, v in pairs(Settings.Selected) do if v then n += 1 end end
    return n
end
UpdateSelectedCount = function() SelectedLabel.Text = "Selected Brainrots: " .. CountSelected() end
UpdateSelectedCount()

local List = Instance.new("ScrollingFrame")
List.Size = UDim2.new(1,0,0,205)
List.Position = UDim2.fromOffset(0,231)
List.BackgroundColor3 = Color3.fromRGB(29,29,35)
List.BorderSizePixel = 0
List.ScrollBarThickness = 5
List.CanvasSize = UDim2.fromOffset(0,0)
List.Parent = Content
local lc = Instance.new("UICorner")
lc.CornerRadius = UDim.new(0,8)
lc.Parent = List
local Layout = Instance.new("UIListLayout")
Layout.Padding = UDim.new(0,3)
Layout.Parent = List

-- FIX: checked targets are always sorted to the top.
local RenderVersion = 0
RenderDatabase = function()
    RenderVersion += 1
    local version = RenderVersion
    for _, child in ipairs(List:GetChildren()) do
        if child ~= Layout then child:Destroy() end
    end

    local query = string.lower(SearchBox.Text)
    local ordered = {}
    for _, name in ipairs(GameData.AnimalNames) do
        if query == "" or string.find(string.lower(name), query, 1, true) then
            ordered[#ordered + 1] = name
        end
    end

    table.sort(ordered, function(a, b)
        local aSelected = Settings.Selected[a] == true
        local bSelected = Settings.Selected[b] == true
        if aSelected ~= bSelected then return aSelected end
        local ad = GetAnimalData(a)
        local bd = GetAnimalData(b)
        local ag = ad and ad.Generation or 0
        local bg = bd and bd.Generation or 0
        if ag ~= bg then return ag > bg end
        return a < b
    end)

    local added = 0
    for _, name in ipairs(ordered) do
        if version ~= RenderVersion then return end
        local data = GetAnimalData(name)
        local b = Instance.new("TextButton")
        b.Size = UDim2.new(1,-7,0,30)
        b.BorderSizePixel = 0
        b.TextXAlignment = Enum.TextXAlignment.Left
        b.Font = Enum.Font.Gotham
        b.TextSize = 10
        b.TextColor3 = Color3.new(1,1,1)
        b.Parent = List

        local function refreshRow()
            local selected = Settings.Selected[name] == true
            b.BackgroundColor3 = selected and Color3.fromRGB(40,110,65) or Color3.fromRGB(42,42,49)
            b.Text = (selected and "  ✓ " or "    ") .. name .. " | " .. ((data and data.Rarity) or "?") .. " | $" .. FormatMoney(data and data.Generation) .. "/s"
        end
        refreshRow()

        -- Clicking again explicitly unchecks it.
        b.MouseButton1Click:Connect(function()
            if Settings.Selected[name] then
                Settings.Selected[name] = nil
            else
                Settings.Selected[name] = true
            end
            UpdateSelectedCount()
            QueueSave()
            -- Re-render immediately so selected rows jump to top / unchecked rows return to normal position.
            RenderDatabase()
        end)

        added += 1
        if added >= MAX_VISIBLE_ROWS then break end
    end

    task.defer(function()
        if List.Parent then List.CanvasSize = UDim2.fromOffset(0, Layout.AbsoluteContentSize.Y + 5) end
    end)
end

local SearchToken = 0
Track(SearchBox:GetPropertyChangedSignal("Text"):Connect(function()
    SearchToken += 1
    local token = SearchToken
    task.delay(0.12, function()
        if token == SearchToken and not State.Dead then RenderDatabase() end
    end)
end))
Track(ClearButton.MouseButton1Click:Connect(function()
    Settings.Selected = {}
    UpdateSelectedCount()
    RenderDatabase()
    QueueSave()
end))

CreateToggle("WEBHOOK", UDim2.fromOffset(0,444), UDim2.fromOffset(105,32), function() return Settings.WebhookEnabled end, function(v) Settings.WebhookEnabled = v end)
local WebhookInput = Instance.new("TextBox")
WebhookInput.Size = UDim2.new(1,-113,0,32)
WebhookInput.Position = UDim2.fromOffset(113,444)
WebhookInput.BackgroundColor3 = Color3.fromRGB(35,35,42)
WebhookInput.BorderSizePixel = 0
WebhookInput.PlaceholderText = "Discord webhook URL"
WebhookInput.Text = Settings.WebhookURL
WebhookInput.TextColor3 = Color3.new(1,1,1)
WebhookInput.Font = Enum.Font.Gotham
WebhookInput.TextSize = 9
WebhookInput.ClearTextOnFocus = false
WebhookInput.Parent = Content
local wc = Instance.new("UICorner")
wc.CornerRadius = UDim.new(0,8)
wc.Parent = WebhookInput
Track(WebhookInput.FocusLost:Connect(function() Settings.WebhookURL = WebhookInput.Text; QueueSave() end))

local MentionInput = Instance.new("TextBox")
MentionInput.Size = UDim2.new(1,-120,0,32)
MentionInput.Position = UDim2.fromOffset(0,484)
MentionInput.BackgroundColor3 = Color3.fromRGB(35,35,42)
MentionInput.BorderSizePixel = 0
MentionInput.PlaceholderText = "Optional ping: <@DiscordUserID>"
MentionInput.Text = Settings.WebhookMention
MentionInput.TextColor3 = Color3.new(1,1,1)
MentionInput.Font = Enum.Font.Gotham
MentionInput.TextSize = 9
MentionInput.ClearTextOnFocus = false
MentionInput.Parent = Content
local mnc = Instance.new("UICorner")
mnc.CornerRadius = UDim.new(0,8)
mnc.Parent = MentionInput
Track(MentionInput.FocusLost:Connect(function() Settings.WebhookMention = MentionInput.Text; QueueSave() end))

local StartButton = Instance.new("TextButton")
StartButton.Size = UDim2.fromOffset(112,32)
StartButton.Position = UDim2.new(1,-112,0,484)
StartButton.BackgroundColor3 = Color3.fromRGB(45,155,78)
StartButton.BorderSizePixel = 0
StartButton.Text = "START"
StartButton.TextColor3 = Color3.new(1,1,1)
StartButton.Font = Enum.Font.GothamBold
StartButton.TextSize = 11
StartButton.Parent = Content
local sbc = Instance.new("UICorner")
sbc.CornerRadius = UDim.new(0,8)
sbc.Parent = StartButton

--==============================================================
-- CLEANUP
--==============================================================
function State.Cleanup()
    State.Running = false
    State.Dead = true
    SaveNow()
    for _, conn in ipairs(State.Connections) do pcall(function() conn:Disconnect() end) end
    table.clear(State.Connections)
    if State.GUI then pcall(function() State.GUI:Destroy() end) end
    if ENV[SCRIPT_KEY] == State then ENV[SCRIPT_KEY] = nil end
end

Track(Player.CharacterAdded:Connect(function()
    task.wait(0.7)
    if not State.Dead then LoadCharacter() end
end))

--==============================================================
-- FILTER
--==============================================================
local function ShouldBuy(model, mutation)
    local data = GetAnimalData(model.Name)
    local base = data and data.Generation or nil
    local actual = GetEffectiveGeneration(base, mutation)
    local nameMatch, moneyMatch = false, false

    if Settings.NameFilter then
        nameMatch = Settings.Selected[model.Name] == true
        if not nameMatch and data then
            if data.Name then nameMatch = Settings.Selected[data.Name] == true end
            if not nameMatch and data.InternalKey then nameMatch = Settings.Selected[data.InternalKey] == true end
        end
    end

    if Settings.MoneyFilter and actual ~= nil then
        moneyMatch = actual >= Settings.MinGeneration
    end

    return nameMatch or moneyMatch, data, nameMatch, moneyMatch, actual
end

--==============================================================
-- SPIN RESULT SYNCHRONIZATION
--==============================================================
-- FIX: result detection is based on the model actually moving from the parked
-- Y=100000 area to the machine. It does NOT depend on the buy prompt existing.
local function SpinAndWaitForNext(currentModel)
    local old = currentModel or GetActiveBrainrot()
    local sawGap = (old == nil)

    while State.Running and not State.Dead do
        if not PromptBusy[SpinPrompt] and SpinPrompt.Parent and SpinPrompt.Enabled then
            local fired = FirePromptOnce(SpinPrompt)
            if fired then
                local started = os.clock()
                while State.Running and not State.Dead and os.clock() - started < SPIN_RESULT_TIMEOUT do
                    if old and not IsDisplayedResult(old) then sawGap = true end
                    local active = GetActiveBrainrot()

                    if active then
                        if not old then
                            return active
                        end
                        if active ~= old then
                            return active
                        end
                        if sawGap and active == old then
                            return active
                        end
                    end
                    task.wait(SCAN_INTERVAL)
                end
            end
        end
        task.wait(SPIN_RETRY_GAP)
    end
    return nil
end

--==============================================================
-- BUY
--==============================================================
local function WaitForBuyPrompt(model, timeout)
    local started = os.clock()
    while State.Running and not State.Dead and os.clock() - started < timeout do
        if not IsDisplayedResult(model) then return nil end
        local prompt = GetBuyPrompt(model)
        if prompt and prompt.Enabled then return prompt end
        task.wait(0.03)
    end
    return GetBuyPrompt(model)
end

local function BuyUntilGone(model)
    local started = os.clock()
    local attempts = 0

    while State.Running and not State.Dead and os.clock() - started < MAX_BUY_TIME do
        if not IsDisplayedResult(model) then
            SetStatus("Purchased / result removed")
            return true
        end

        local prompt = WaitForBuyPrompt(model, BUY_PROMPT_WAIT)
        if prompt and prompt.Parent and prompt.Enabled and not PromptBusy[prompt] then
            if FirePromptOnce(prompt) then
                attempts += 1
                -- Let the full hold finish before attempting another purchase.
                local waitUntil = os.clock() + math.max(prompt.HoldDuration, 0.05) + 0.22
                while State.Running and not State.Dead and os.clock() < waitUntil do
                    if not IsDisplayedResult(model) then
                        SetStatus("Purchased / result removed")
                        return true
                    end
                    task.wait(0.03)
                end
            end
        end
        task.wait(BUY_RETRY_GAP)
    end

    SetStatus("Purchase timeout (" .. attempts .. " tries)")
    return false
end

--==============================================================
-- MAIN
--==============================================================
local Spins = 0
local function MainLoop()
    if State.LoopRunning then return end
    State.LoopRunning = true

    if not GameData.Ready then
        SetStatus("Waiting for database...")
        while State.Running and not State.Dead and not GameData.Ready do task.wait(0.1) end
    end
    if not State.Running or State.Dead then State.LoopRunning = false; return end

    SetStatus("Walking to spinner...")
    if not MoveTo(SPIN_POSITION) then State.LoopRunning = false; return end

    SetStatus("Spinning...")
    local current = SpinAndWaitForNext(nil)

    while State.Running and not State.Dead do
        if not current then
            current = SpinAndWaitForNext(nil)
            continue
        end

        -- A confirmed new displayed result increments the counter.
        Spins += 1

        local mutation = DetectMutation(current)
        local buy, data, nameMatch, moneyMatch, actual = ShouldBuy(current, mutation)
        local rarity = data and data.Rarity or "?"
        local mult = GetMutationMultiplier(mutation)

        ResultLabel.Text = "Spins: " .. tostring(Spins)
            .. "\n" .. current.Name
            .. " | " .. mutation
            .. " | " .. rarity
            .. " | $" .. FormatMoney(actual) .. "/s"
            .. (mutation ~= "Normal" and (" | " .. string.format("%.3gx", mult)) or "")

        print("[SmileB RNG] RESULT", Spins, current.Name, "income", actual, "nameMatch", nameMatch, "moneyMatch", moneyMatch)

        if buy then
            local reason = (nameMatch and moneyMatch) and "Name + Money" or (nameMatch and "Name" or "Money")
            SetStatus("FOUND: " .. reason .. " | buying...")
            SendWebhook(current.Name, data, mutation, actual, reason)

            if MoveTo(BUY_POSITION) then
                BuyUntilGone(current)
            end

            if not State.Running then break end
            SetStatus("Returning to spinner...")
            MoveTo(SPIN_POSITION)
            if not State.Running then break end
            SetStatus("Spinning...")
            current = SpinAndWaitForNext(nil)
        else
            SetStatus("Skip | spinning again")
            current = SpinAndWaitForNext(current)
        end
    end

    State.LoopRunning = false
    if not State.Dead then SetStatus("Stopped") end
end

Track(StartButton.MouseButton1Click:Connect(function()
    ApplyMoneyInput()
    Settings.WebhookURL = WebhookInput.Text
    Settings.WebhookMention = MentionInput.Text
    QueueSave()

    State.Running = not State.Running
    if State.Running then
        StartButton.Text = "STOP"
        StartButton.BackgroundColor3 = Color3.fromRGB(180,55,55)
        task.spawn(function()
            local ok, err = pcall(MainLoop)
            if not ok then
                warn("[SmileB RNG]", err)
                SetStatus("ERROR: " .. tostring(err))
            end
            State.Running = false
            State.LoopRunning = false
            if not State.Dead and StartButton.Parent then
                StartButton.Text = "START"
                StartButton.BackgroundColor3 = Color3.fromRGB(45,155,78)
            end
        end)
    else
        StartButton.Text = "START"
        StartButton.BackgroundColor3 = Color3.fromRGB(45,155,78)
        SetStatus("Stopping...")
    end
end))

--==============================================================
-- DATA REFRESH
--==============================================================
task.spawn(RefreshGameData)
task.spawn(function()
    while not State.Dead do
        task.wait(5)
        if Settings.AutoRefresh and not GameData.Refreshing and os.clock() - GameData.LastRefresh >= DATA_REFRESH_SECONDS then
            task.spawn(RefreshGameData)
        end
    end
end)

if Settings.Minimized then
    task.defer(function()
        task.wait(0.15)
        if not State.Dead and not State.Minimized then MinimizeUI() end
    end)
end

print("[SmileB RNG] Loaded")
print("[SmileB RNG] Fixed result detection, counter, name/money targeting, and selected sorting")