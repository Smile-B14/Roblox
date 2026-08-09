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

local SPIN_POSITION = Vector3.new(-384, -6, 68)
local BUY_POSITION = Vector3.new(-378, -6, 73)
local ARRIVAL_DISTANCE = 3.5
local ACTIVE_RANGE = 45
local SCAN_INTERVAL = 0.025
local SPIN_RESULT_TIMEOUT = 3.0
local SPIN_RETRY_GAP = 0.20
local BUY_RETRY_GAP = 0.08
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

local function HasFileSupport()
    return typeof(writefile) == "function" and typeof(readfile) == "function" and typeof(isfile) == "function"
end

local function SelectedToArray()
    local out = {}
    for name, enabled in pairs(Settings.Selected) do
        if enabled then out[#out + 1] = name end
    end
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
    local s = tostring(text or "")
    s = s:gsub(",", "")
    s = s:gsub("%$", "")
    s = s:gsub("%s", "")
    s = s:lower()
    local mult = 1
    local suffix = s:sub(-1)
    if suffix == "k" then mult = 1e3; s = s:sub(1, -2)
    elseif suffix == "m" then mult = 1e6; s = s:sub(1, -2)
    elseif suffix == "b" then mult = 1e9; s = s:sub(1, -2)
    elseif suffix == "t" then mult = 1e12; s = s:sub(1, -2)
    elseif suffix == "q" then mult = 1e15; s = s:sub(1, -2) end
    local n = tonumber(s)
    return n and n * mult or nil
end

local function DecompileWithTimeout(module, timeout)
    if typeof(decompile) ~= "function" then return nil end
    local done, ok, result = false, false, nil
    task.spawn(function()
        ok, result = pcall(decompile, module)
        done = true
    end)
    local started = os.clock()
    while not done and not State.Dead and os.clock() - started < timeout do task.wait(0.05) end
    if done and ok and typeof(result) == "string" then return result end
    return nil
end

local function FindEntryKey(source, displayStart, displayName)
    local prefix = source:sub(math.max(1, displayStart - 500), displayStart - 1)
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
        local chunk = source:sub(s, nextDisplay and nextDisplay - 1 or math.min(#source, e + 1800))
        local internalKey = FindEntryKey(source, s, displayName)
        local data = {
            Name = displayName,
            InternalKey = internalKey,
            Rarity = chunk:match('Rarity%s*=%s*"([^"]+)"'),
            Generation = tonumber(chunk:match("Generation%s*=%s*([%d%.eE%-]+)") or ""),
            Price = tonumber(chunk:match("Price%s*=%s*([%d%.eE%-]+)") or ""),
        }
        db[displayName] = data
        if internalKey then db[internalKey] = data end
        if not seen[displayName] then seen[displayName] = true; names[#names + 1] = displayName end
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
    local s = tostring(name or ""):lower()
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
        local chunk = source:sub(s, nextDisplay and nextDisplay - 1 or math.min(#source, e + 1500))
        local key = FindEntryKey(source, s, displayText)
        local data = { Key = key, DisplayText = displayText, Modifier = tonumber(chunk:match("Modifier%s*=%s*([%d%.eE%-]+)") or "") or 0 }
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

local function GetAnimalData(name) return GameData.Animals[name] end
local function GetMutationData(name)
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
            if tostring(key):lower():find("mutation", 1, true) then
                local found = MatchMutationValue(value)
                if found then return found end
            end
            if value == true then
                local found = MatchMutationValue(key)
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
        local found = MatchMutationValue(d.Name)
        if found then return found end
    end
    return "Normal"
end

local PromptBusy = setmetatable({}, { __mode = "k" })
local function FirePromptOnce(prompt)
    if not prompt or not prompt.Parent or not prompt.Enabled then return false end
    if typeof(fireproximityprompt) ~= "function" or PromptBusy[prompt] then return false end
    PromptBusy[prompt] = true
    local ok = pcall(function() fireproximityprompt(prompt) end)
    local hold = tonumber(prompt.HoldDuration) or 0
    task.delay(math.max(hold, 0.05) + 0.18, function() PromptBusy[prompt] = nil end)
    return ok
end

local function InstancePosition(obj)
    if not obj then return nil end
    if obj:IsA("Attachment") then return obj.WorldPosition end
    if obj:IsA("BasePart") then return obj.Position end
    if obj:IsA("Model") then
        local ok, cf = pcall(obj.GetPivot, obj)
        if ok then return cf.Position end
        local part = obj:FindFirstChildWhichIsA("BasePart", true)
        return part and part.Position or nil
    end
    local parent = obj.Parent
    if parent and parent:IsA("Attachment") then return parent.WorldPosition end
    if parent and parent:IsA("BasePart") then return parent.Position end
    return nil
end

local function AimCamera(target)
    local camera = workspace.CurrentCamera
    if not camera then return end
    local pos = typeof(target) == "Vector3" and target or (typeof(target) == "Instance" and InstancePosition(target))
    if not pos then return end
    pcall(function()
        TweenService:Create(camera, TweenInfo.new(0.16, Enum.EasingStyle.Quad, Enum.EasingDirection.Out), {
            CFrame = CFrame.lookAt(camera.CFrame.Position, pos)
        }):Play()
    end)
end

local function FaceTarget(pos)
    if not Root or not pos then return end
    local flat = Vector3.new(pos.X, Root.Position.Y, pos.Z)
    if (flat - Root.Position).Magnitude > 0.01 then
        pcall(function() Root.CFrame = CFrame.lookAt(Root.Position, flat) end)
    end
end

local function GetBuyPrompt(model)
    local root = model and model:FindFirstChild("RootPart")
    local attachment = root and root:FindFirstChild("PromptAttachment")
    return attachment and attachment:FindFirstChildWhichIsA("ProximityPrompt") or nil
end

local function IsActiveBrainrot(model)
    if not model or not model.Parent or not model:IsA("Model") then return false end
    local root = model:FindFirstChild("RootPart")
    return root and (root.Position - BUY_POSITION).Magnitude < ACTIVE_RANGE or false
end

local function GetActiveBrainrot()
    local folder = workspace:FindFirstChild("RNGMachineDisplay")
    if not folder then return nil end
    local best, bestDistance = nil, math.huge
    for _, model in ipairs(folder:GetChildren()) do
        local root = model:IsA("Model") and model:FindFirstChild("RootPart")
        if root then
            local d = (root.Position - BUY_POSITION).Magnitude
            if d < ACTIVE_RANGE and d < bestDistance then best, bestDistance = model, d end
        end
    end
    return best
end

local function FlatDistance(a, b)
    local dx, dz = a.X - b.X, a.Z - b.Z
    return math.sqrt(dx * dx + dz * dz)
end

local function MoveDirect(position, timeout)
    Humanoid:MoveTo(position)
    local started = os.clock()
    while State.Running and not State.Dead do
        if FlatDistance(Root.Position, position) <= ARRIVAL_DISTANCE then return true end
        if os.clock() - started >= (timeout or 4) then return false end
        task.wait(0.05)
    end
    return false
end

local function ComputePathTo(position)
    local path = PathfindingService:CreatePath({ AgentRadius = 2, AgentHeight = 5, AgentCanJump = true, AgentJumpHeight = 7, AgentMaxSlope = 45 })
    local ok = pcall(function() path:ComputeAsync(Root.Position, position) end)
    if ok and path.Status == Enum.PathStatus.Success then return path:GetWaypoints() end
    return nil
end

local function MoveAdaptive(position, maxAttempts)
    if not State.Running or State.Dead then return false end
    if not Root or not Root.Parent then LoadCharacter() end
    if FlatDistance(Root.Position, position) <= ARRIVAL_DISTANCE then return true end
    maxAttempts = maxAttempts or 5

    for attempt = 1, maxAttempts do
        if not State.Running or State.Dead then return false end
        local waypoints = ComputePathTo(position)
        if waypoints then
            local failed = false
            for _, waypoint in ipairs(waypoints) do
                if waypoint.Action == Enum.PathWaypointAction.Jump then Humanoid.Jump = true end
                Humanoid:MoveTo(waypoint.Position)
                local started = os.clock()
                local lastPos = Root.Position
                local lastMove = os.clock()
                while State.Running and not State.Dead and FlatDistance(Root.Position, waypoint.Position) > ARRIVAL_DISTANCE do
                    if (Root.Position - lastPos).Magnitude > 0.6 then
                        lastPos = Root.Position
                        lastMove = os.clock()
                    elseif os.clock() - lastMove > 0.9 then
                        failed = true
                        break
                    end
                    if os.clock() - started > 3 then failed = true; break end
                    task.wait(0.04)
                end
                if failed then break end
            end
            if not failed and FlatDistance(Root.Position, position) <= 7 then return true end
        elseif MoveDirect(position, 1.5) then
            return true
        end

        -- Stuck recovery: jump and sidestep, then calculate a fresh path.
        Humanoid.Jump = true
        local side = (attempt % 2 == 0 and -1 or 1)
        local sidePos = Root.Position + Root.CFrame.RightVector * (3.5 * side) + Root.CFrame.LookVector * 1.5
        Humanoid:MoveTo(sidePos)
        task.wait(0.35)
    end

    return MoveDirect(position, 3)
end

local function PrepareSpinner()
    if not MoveAdaptive(SPIN_POSITION, 4) then return false end
    local promptPos = InstancePosition(SpinPrompt)
    if promptPos then
        FaceTarget(promptPos)
        AimCamera(promptPos)
    end
    task.wait(0.12)
    return true
end

local function GetHoney()
    return workspace:FindFirstChild("Honey")
end

local function HoneyPosition(honey)
    return InstancePosition(honey)
end

local function CollectHoneyIfPresent()
    local honey = GetHoney()
    if not honey or not honey.Parent then return false end
    local hp = HoneyPosition(honey)
    if not hp then return false end

    local old = honey
    local started = os.clock()
    while State.Running and not State.Dead and old.Parent and os.clock() - started < 10 do
        hp = HoneyPosition(old)
        if not hp then break end
        FaceTarget(hp)
        AimCamera(hp)
        MoveAdaptive(hp, 5)
        if not old.Parent or workspace:FindFirstChild("Honey") ~= old then break end
        if FlatDistance(Root.Position, hp) <= 4.5 then
            Humanoid.Jump = true
            Humanoid:MoveTo(hp)
            task.wait(0.35)
        else
            task.wait(0.15)
        end
    end
    return true
end

local function GetRequestFunction()
    if typeof(request) == "function" then return request end
    if typeof(http_request) == "function" then return http_request end
    if typeof(syn) == "table" and typeof(syn.request) == "function" then return syn.request end
    return nil
end

local function SendWebhook(name, data, mutation, actualGeneration, reason)
    if not Settings.WebhookEnabled or Settings.WebhookURL == "" then return end
    local requestFn = GetRequestFunction()
    if not requestFn then return end
    local url, mention = Settings.WebhookURL, Settings.WebhookMention
    task.spawn(function()
        local description = "**Brainrot:** " .. tostring(name)
            .. "\n**Mutation:** " .. tostring(mutation)
            .. "\n**Rarity:** " .. tostring(data and data.Rarity or "?")
            .. "\n**Income:** $" .. FormatMoney(actualGeneration) .. "/s"
            .. "\n**Matched by:** " .. tostring(reason)
        if mutation ~= "Normal" then
            description ..= "\n**Base:** $" .. FormatMoney(data and data.Generation) .. "/s"
                .. "\n**Multiplier:** " .. string.format("%.3gx", GetMutationMultiplier(mutation))
        end
        local payload = { embeds = { { title = "RNG Target Found", description = description } } }
        if mention ~= "" then payload.content = mention end
        local ok, body = pcall(HttpService.JSONEncode, HttpService, payload)
        if ok then pcall(requestFn, { Url = url, Method = "POST", Headers = { ["Content-Type"] = "application/json" }, Body = body }) end
    end)
end

-- UI
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
local FrameCorner = Instance.new("UICorner", Frame)
FrameCorner.CornerRadius = UDim.new(0, 12)

local TitleBar = Instance.new("Frame", Frame)
TitleBar.Size = UDim2.new(1,0,0,44)
TitleBar.BackgroundTransparency = 1
local Title = Instance.new("TextLabel", TitleBar)
Title.Size = UDim2.new(1,-100,1,0)
Title.Position = UDim2.fromOffset(14,0)
Title.BackgroundTransparency = 1
Title.Text = "RNG Auto Buyer"
Title.TextXAlignment = Enum.TextXAlignment.Left
Title.Font = Enum.Font.GothamBold
Title.TextSize = 16
Title.TextColor3 = Color3.new(1,1,1)
local MinimizeButton = Instance.new("TextButton", TitleBar)
MinimizeButton.Size = UDim2.fromOffset(38,30)
MinimizeButton.Position = UDim2.new(1,-47,0,7)
MinimizeButton.BackgroundColor3 = Color3.fromRGB(42,42,48)
MinimizeButton.BorderSizePixel = 0
MinimizeButton.Text = "−"
MinimizeButton.TextColor3 = Color3.new(1,1,1)
MinimizeButton.TextSize = 20

local Content = Instance.new("Frame", Frame)
Content.Size = UDim2.new(1,-20,1,-54)
Content.Position = UDim2.fromOffset(10,46)
Content.BackgroundTransparency = 1

local MiniButton = Instance.new("TextButton", Frame)
MiniButton.Size = UDim2.fromScale(1,1)
MiniButton.BackgroundTransparency = 1
MiniButton.Text = "🍯"
MiniButton.TextColor3 = Color3.new(1,1,1)
MiniButton.TextSize = 28
MiniButton.Font = Enum.Font.GothamBold
MiniButton.Visible = false

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

local Animating = false
local function OpenUI()
    if not State.Minimized or Animating then return end
    Animating = true
    State.Minimized = false
    TweenService:Create(MiniButton, TweenInfo.new(0.32, Enum.EasingStyle.Back), { Rotation = MiniButton.Rotation + 360 }):Play()
    local tween = TweenService:Create(Frame, TweenInfo.new(0.28, Enum.EasingStyle.Quint), { Size = UDim2.fromOffset(WINDOW_WIDTH, WINDOW_HEIGHT) })
    tween:Play(); tween.Completed:Wait()
    MiniButton.Visible = false
    TitleBar.Visible = true
    Content.Visible = true
    Animating = false
    QueueSave()
end
local function MinimizeUI()
    if State.Minimized or Animating then return end
    Animating = true
    State.Minimized = true
    TitleBar.Visible = false
    Content.Visible = false
    MiniButton.Visible = true
    MiniButton.Rotation = 0
    TweenService:Create(MiniButton, TweenInfo.new(0.35, Enum.EasingStyle.Back), { Rotation = 360 }):Play()
    local tween = TweenService:Create(Frame, TweenInfo.new(0.28, Enum.EasingStyle.Quint), { Size = UDim2.fromOffset(MINI_SIZE, MINI_SIZE) })
    tween:Play(); tween.Completed:Wait()
    Animating = false
    QueueSave()
end
Track(MinimizeButton.MouseButton1Click:Connect(MinimizeUI))
AttachDrag(TitleBar, false, nil)
AttachDrag(MiniButton, true, OpenUI)

local function MakeLabel(y, h, text, size)
    local l = Instance.new("TextLabel", Content)
    l.Position = UDim2.fromOffset(0,y)
    l.Size = UDim2.new(1,0,0,h)
    l.BackgroundTransparency = 1
    l.Text = text
    l.TextColor3 = Color3.fromRGB(190,190,195)
    l.TextXAlignment = Enum.TextXAlignment.Left
    l.Font = Enum.Font.Gotham
    l.TextSize = size or 10
    return l
end
local DatabaseStatus = MakeLabel(0,20,"Loading live data...",10)
UpdateDatabaseStatus = function(text) DatabaseStatus.Text = text end
local Status = MakeLabel(21,22,"Ready",11)
local function SetStatus(text) Status.Text = text end
local ResultLabel = MakeLabel(43,48,"Spins: 0\nNo result yet",11)
ResultLabel.TextYAlignment = Enum.TextYAlignment.Top
ResultLabel.TextWrapped = true

local function CreateToggle(text, x, getter, setter)
    local b = Instance.new("TextButton", Content)
    b.Position = UDim2.fromOffset(x,96)
    b.Size = UDim2.fromOffset(x == 266 and 134 or 125,32)
    b.BorderSizePixel = 0
    b.TextColor3 = Color3.new(1,1,1)
    b.Font = Enum.Font.GothamBold
    b.TextSize = 10
    local function refreshButton()
        local enabled = getter()
        b.Text = text .. ": " .. (enabled and "ON" or "OFF")
        b.BackgroundColor3 = enabled and Color3.fromRGB(45,145,75) or Color3.fromRGB(72,72,80)
    end
    Track(b.MouseButton1Click:Connect(function() setter(not getter()); refreshButton(); QueueSave() end))
    refreshButton()
    return b
end
CreateToggle("NAME",0,function() return Settings.NameFilter end,function(v) Settings.NameFilter=v end)
CreateToggle("MONEY",133,function() return Settings.MoneyFilter end,function(v) Settings.MoneyFilter=v end)
CreateToggle("AUTO DATA",266,function() return Settings.AutoRefresh end,function(v) Settings.AutoRefresh=v end)

local MoneyInput = Instance.new("TextBox", Content)
MoneyInput.Position = UDim2.fromOffset(0,135)
MoneyInput.Size = UDim2.new(1,0,0,34)
MoneyInput.BackgroundColor3 = Color3.fromRGB(35,35,42)
MoneyInput.BorderSizePixel = 0
MoneyInput.TextColor3 = Color3.new(1,1,1)
MoneyInput.PlaceholderText = "Minimum final income >= e.g. 10M"
MoneyInput.Text = tostring(Settings.MinGeneration)
MoneyInput.ClearTextOnFocus = false
MoneyInput.Font = Enum.Font.Gotham
MoneyInput.TextSize = 11
local function ApplyMoneyInput()
    local value = ParseNumber(MoneyInput.Text)
    if value then Settings.MinGeneration=value;MoneyInput.Text=tostring(value);QueueSave() else MoneyInput.Text=tostring(Settings.MinGeneration) end
end
Track(MoneyInput.FocusLost:Connect(ApplyMoneyInput))

local SearchBox = Instance.new("TextBox", Content)
SearchBox.Position = UDim2.fromOffset(0,177)
SearchBox.Size = UDim2.new(1,-100,0,32)
SearchBox.BackgroundColor3 = Color3.fromRGB(35,35,42)
SearchBox.BorderSizePixel = 0
SearchBox.TextColor3 = Color3.new(1,1,1)
SearchBox.PlaceholderText = "Search Brainrots..."
SearchBox.Text = ""
SearchBox.Font = Enum.Font.Gotham
SearchBox.TextSize = 11
local ClearButton = Instance.new("TextButton", Content)
ClearButton.Position = UDim2.new(1,-92,0,177)
ClearButton.Size = UDim2.fromOffset(92,32)
ClearButton.Text = "CLEAR"
ClearButton.BackgroundColor3 = Color3.fromRGB(65,65,73)
ClearButton.TextColor3 = Color3.new(1,1,1)
ClearButton.BorderSizePixel = 0
ClearButton.Font = Enum.Font.GothamBold
ClearButton.TextSize = 10

local SelectedLabel = MakeLabel(211,18,"Selected: 0",10)
local function CountSelected() local n=0;for _,v in pairs(Settings.Selected) do if v then n+=1 end end;return n end
UpdateSelectedCount = function() SelectedLabel.Text = "Selected Brainrots: " .. CountSelected() end
UpdateSelectedCount()

local List = Instance.new("ScrollingFrame", Content)
List.Position = UDim2.fromOffset(0,231)
List.Size = UDim2.new(1,0,0,205)
List.BackgroundColor3 = Color3.fromRGB(29,29,35)
List.BorderSizePixel = 0
List.ScrollBarThickness = 5
local Layout = Instance.new("UIListLayout", List)
Layout.Padding = UDim.new(0,3)

local RenderVersion = 0
RenderDatabase = function()
    RenderVersion += 1
    local myVersion = RenderVersion
    for _, child in ipairs(List:GetChildren()) do if child ~= Layout then child:Destroy() end end
    local query = SearchBox.Text:lower()
    local candidates = {}
    for _, name in ipairs(GameData.AnimalNames) do
        if query == "" or name:lower():find(query,1,true) then candidates[#candidates+1]=name end
    end
    table.sort(candidates,function(a,b)
        local sa,sb=Settings.Selected[a]==true,Settings.Selected[b]==true
        if sa~=sb then return sa end
        local ga=(GetAnimalData(a) and GetAnimalData(a).Generation) or 0
        local gb=(GetAnimalData(b) and GetAnimalData(b).Generation) or 0
        if ga~=gb then return ga>gb end
        return a<b
    end)
    local added=0
    for _, name in ipairs(candidates) do
        if myVersion~=RenderVersion then return end
        local data=GetAnimalData(name)
        local b=Instance.new("TextButton",List)
        b.Size=UDim2.new(1,-7,0,30);b.BorderSizePixel=0;b.TextXAlignment=Enum.TextXAlignment.Left;b.Font=Enum.Font.Gotham;b.TextSize=10;b.TextColor3=Color3.new(1,1,1)
        local function row()
            local selected=Settings.Selected[name]==true
            b.BackgroundColor3=selected and Color3.fromRGB(40,110,65) or Color3.fromRGB(42,42,49)
            b.Text=(selected and "  ✓ " or "    ")..name.." | "..tostring(data and data.Rarity or "?").." | $"..FormatMoney(data and data.Generation).."/s"
        end
        row()
        Track(b.MouseButton1Click:Connect(function()
            if Settings.Selected[name] then Settings.Selected[name]=nil else Settings.Selected[name]=true end
            UpdateSelectedCount();QueueSave();RenderDatabase()
        end))
        added+=1
        if added>=MAX_VISIBLE_ROWS then break end
    end
    task.defer(function() if List.Parent then List.CanvasSize=UDim2.fromOffset(0,Layout.AbsoluteContentSize.Y+5) end end)
end
local SearchToken=0
Track(SearchBox:GetPropertyChangedSignal("Text"):Connect(function()
    SearchToken+=1;local token=SearchToken
    task.delay(.12,function() if token==SearchToken and not State.Dead then RenderDatabase() end end)
end))
Track(ClearButton.MouseButton1Click:Connect(function() Settings.Selected={};UpdateSelectedCount();RenderDatabase();QueueSave() end))

local WebhookToggle=CreateToggle("WEBHOOK",0,function()return Settings.WebhookEnabled end,function(v)Settings.WebhookEnabled=v end)
WebhookToggle.Position=UDim2.fromOffset(0,444)
local WebhookInput=Instance.new("TextBox",Content)
WebhookInput.Position=UDim2.fromOffset(113,444);WebhookInput.Size=UDim2.new(1,-113,0,32);WebhookInput.BackgroundColor3=Color3.fromRGB(35,35,42);WebhookInput.BorderSizePixel=0;WebhookInput.TextColor3=Color3.new(1,1,1);WebhookInput.PlaceholderText="Discord webhook URL";WebhookInput.Text=Settings.WebhookURL;WebhookInput.ClearTextOnFocus=false;WebhookInput.Font=Enum.Font.Gotham;WebhookInput.TextSize=9
Track(WebhookInput.FocusLost:Connect(function()Settings.WebhookURL=WebhookInput.Text;QueueSave()end))
local MentionInput=Instance.new("TextBox",Content)
MentionInput.Position=UDim2.fromOffset(0,484);MentionInput.Size=UDim2.new(1,-120,0,32);MentionInput.BackgroundColor3=Color3.fromRGB(35,35,42);MentionInput.BorderSizePixel=0;MentionInput.TextColor3=Color3.new(1,1,1);MentionInput.PlaceholderText="Optional ping: <@DiscordUserID>";MentionInput.Text=Settings.WebhookMention;MentionInput.ClearTextOnFocus=false;MentionInput.Font=Enum.Font.Gotham;MentionInput.TextSize=9
Track(MentionInput.FocusLost:Connect(function()Settings.WebhookMention=MentionInput.Text;QueueSave()end))
local StartButton=Instance.new("TextButton",Content)
StartButton.Position=UDim2.new(1,-112,0,484);StartButton.Size=UDim2.fromOffset(112,32);StartButton.BackgroundColor3=Color3.fromRGB(45,155,78);StartButton.BorderSizePixel=0;StartButton.Text="START";StartButton.TextColor3=Color3.new(1,1,1);StartButton.Font=Enum.Font.GothamBold;StartButton.TextSize=11

function State.Cleanup()
    State.Running=false
    State.Dead=true
    SaveNow()
    for _,conn in ipairs(State.Connections) do pcall(function()conn:Disconnect()end) end
    table.clear(State.Connections)
    if State.GUI then pcall(function()State.GUI:Destroy()end) end
    if ENV[SCRIPT_KEY]==State then ENV[SCRIPT_KEY]=nil end
end
Track(Player.CharacterAdded:Connect(function()task.wait(.7);if not State.Dead then LoadCharacter()end end))

local function ShouldBuy(model, mutation)
    local data=GetAnimalData(model.Name)
    local actual=GetEffectiveGeneration(data and data.Generation,mutation)
    local nameMatch=false
    local moneyMatch=false
    if Settings.NameFilter then
        nameMatch=Settings.Selected[model.Name]==true
        if not nameMatch and data and data.Name then nameMatch=Settings.Selected[data.Name]==true end
    end
    if Settings.MoneyFilter and actual then moneyMatch=actual>=Settings.MinGeneration end
    return nameMatch or moneyMatch,data,nameMatch,moneyMatch,actual
end

-- One prompt activation only. It does not fire another spin until the current result has been handled.
local function SpinAndWaitForNext(previousModel)
    local previousWasActive=previousModel and IsActiveBrainrot(previousModel) or false
    local sawGap=not previousWasActive
    while State.Running and not State.Dead do
        -- Always be back at the exact start position and looking at the spin prompt before attempting.
        if not PrepareSpinner() then task.wait(.2) continue end
        if not PromptBusy[SpinPrompt] and SpinPrompt.Parent and SpinPrompt.Enabled then
            local promptPos=InstancePosition(SpinPrompt)
            if promptPos then FaceTarget(promptPos);AimCamera(promptPos) end
            if FirePromptOnce(SpinPrompt) then
                local started=os.clock()
                while State.Running and not State.Dead and os.clock()-started<SPIN_RESULT_TIMEOUT do
                    if previousModel and not IsActiveBrainrot(previousModel) then sawGap=true end
                    local active=GetActiveBrainrot()
                    if active then
                        if not previousModel then return active end
                        if active~=previousModel then return active end
                        if sawGap and active==previousModel then return active end
                    end
                    task.wait(SCAN_INTERVAL)
                end
            end
        end
        task.wait(SPIN_RETRY_GAP)
    end
    return nil
end

local function BuyUntilGone(model)
    local started=os.clock()
    local attempts=0
    while State.Running and not State.Dead and os.clock()-started<MAX_BUY_TIME do
        if not IsActiveBrainrot(model) then SetStatus("Purchased / result removed");return true end
        local prompt=GetBuyPrompt(model)
        if prompt and prompt.Enabled then
            local pp=InstancePosition(prompt)
            if pp then FaceTarget(pp);AimCamera(pp) end
            if not PromptBusy[prompt] and FirePromptOnce(prompt) then attempts+=1 end
        else
            task.wait(.03)
        end
        task.wait(BUY_RETRY_GAP)
    end
    SetStatus("Purchase retry timeout ("..attempts..")")
    return false
end

local Spins=0
local function HandleHoneyThenReturn()
    if GetHoney() then
        SetStatus("Honey found | collecting...")
        CollectHoneyIfPresent()
    end
    if State.Running then
        SetStatus("Returning to spinner...")
        PrepareSpinner()
    end
end

local function MainLoop()
    if State.LoopRunning then return end
    State.LoopRunning=true
    if not GameData.Ready then
        SetStatus("Waiting for database...")
        while State.Running and not State.Dead and not GameData.Ready do task.wait(.1) end
    end
    if not State.Running or State.Dead then State.LoopRunning=false;return end

    -- Honey that already exists gets collected before the next spin.
    HandleHoneyThenReturn()
    if not State.Running then State.LoopRunning=false;return end

    local previous=nil
    while State.Running and not State.Dead do
        SetStatus("Spinning...")
        local current=SpinAndWaitForNext(previous)
        if not current then continue end

        -- IMPORTANT: from this point until buying/skip handling is finished, no spin function is called.
        Spins+=1
        local mutation=DetectMutation(current)
        local buy,data,nameMatch,moneyMatch,actual=ShouldBuy(current,mutation)
        local rarity=data and data.Rarity or "?"
        ResultLabel.Text="Spins: "..Spins.."\n"..current.Name.." | "..mutation.." | "..rarity.." | $"..FormatMoney(actual).."/s"..(mutation~="Normal" and (" | "..string.format("%.3gx",GetMutationMultiplier(mutation))) or "")
        print("[SmileB RNG] RESULT",Spins,current.Name,"income",actual,"nameMatch",nameMatch,"moneyMatch",moneyMatch)

        if buy then
            local reason=(nameMatch and moneyMatch) and "Name + Money" or (nameMatch and "Name" or "Money")
            SetStatus("FOUND: "..reason.." | buying FIRST...")
            SendWebhook(current.Name,data,mutation,actual,reason)

            -- Move to buy position and keep camera on the buy prompt. No respin is possible in this section.
            MoveAdaptive(BUY_POSITION,4)
            local bp=GetBuyPrompt(current)
            if bp then local p=InstancePosition(bp);if p then FaceTarget(p);AimCamera(p) end end
            BuyUntilGone(current)

            -- User requested: if Honey exists, buying has priority, then Honey.
            HandleHoneyThenReturn()
            previous=nil
        else
            -- No target purchase needed. Honey is handled before the next spin.
            HandleHoneyThenReturn()
            previous=current
        end
    end

    State.LoopRunning=false
    if not State.Dead then SetStatus("Stopped") end
end

Track(StartButton.MouseButton1Click:Connect(function()
    ApplyMoneyInput()
    Settings.WebhookURL=WebhookInput.Text
    Settings.WebhookMention=MentionInput.Text
    QueueSave()
    State.Running=not State.Running
    if State.Running then
        StartButton.Text="STOP";StartButton.BackgroundColor3=Color3.fromRGB(180,55,55)
        task.spawn(function()
            local ok,err=pcall(MainLoop)
            if not ok then warn("[SmileB RNG]",err);SetStatus("ERROR: "..tostring(err)) end
            State.Running=false;State.LoopRunning=false
            if not State.Dead and StartButton.Parent then StartButton.Text="START";StartButton.BackgroundColor3=Color3.fromRGB(45,155,78) end
        end)
    else
        StartButton.Text="START";StartButton.BackgroundColor3=Color3.fromRGB(45,155,78);SetStatus("Stopping...")
    end
end))

task.spawn(RefreshGameData)
task.spawn(function()
    while not State.Dead do
        task.wait(5)
        if Settings.AutoRefresh and not GameData.Refreshing and os.clock()-GameData.LastRefresh>=DATA_REFRESH_SECONDS then task.spawn(RefreshGameData) end
    end
end)

if Settings.Minimized then task.defer(function()task.wait(.15);if not State.Dead and not State.Minimized then MinimizeUI()end end) end

print("[SmileB RNG] Loaded")
print("[SmileB RNG] Buy-before-respin flow enabled")
print("[SmileB RNG] Start-position + camera prompt aiming enabled")
print("[SmileB RNG] Honey collector enabled")