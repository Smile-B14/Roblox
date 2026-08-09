-- Smile B dynamic RNG auto buyer
-- State flow: START -> SPIN -> WAIT UNTIL BUY PROMPT EXISTS -> FILTER -> BUY IF WANTED -> HONEY -> START -> NEXT SPIN

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local PathfindingService = game:GetService("PathfindingService")
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")
local RunService = game:GetService("RunService")
local HttpService = game:GetService("HttpService")

local Player = Players.LocalPlayer
local ENV = getgenv and getgenv() or _G
local SCRIPT_KEY = "SmileB_RNG_AutoBuyer_FinalDynamic"
local VERSION = "2026-08-09-ready-lock-v1"

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
    Phase = "IDLE",
}
ENV[SCRIPT_KEY] = State

local SPIN_POSITION = Vector3.new(-384, -6, 68)
local BUY_POSITION = Vector3.new(-378, -6, 73)
local ARRIVAL_DISTANCE = 3.8
local ACTIVE_RANGE = 100
local RESULT_READY_TIMEOUT = 10
local SPIN_TRANSITION_TIMEOUT = 8
local BUY_SAFETY_TIMEOUT = 20
local HONEY_SAFETY_TIMEOUT = 12
local SCAN_INTERVAL = 0.025
local DATA_REFRESH_SECONDS = 300
local PARSE_YIELD_EVERY = 40
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

local function Track(c)
    State.Connections[#State.Connections + 1] = c
    return c
end

local function HasFileSupport()
    return typeof(writefile) == "function" and typeof(readfile) == "function" and typeof(isfile) == "function"
end

local function SelectedArray()
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
        Selected = SelectedArray(),
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

local saveQueued = false
local function QueueSave()
    if saveQueued then return end
    saveQueued = true
    task.delay(.3, function()
        saveQueued = false
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
    warn("[SmileB RNG] RNGMachinePrompt missing")
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
    if typeof(text) ~= "string" then return tonumber(text) end
    local s = text
    s = s:gsub(",", "")
    s = s:gsub("%$", "")
    s = s:gsub("%s", "")
    s = s:lower()
    local mult = 1
    local suffix = s:sub(-1)
    if suffix == "k" then mult = 1e3; s = s:sub(1,-2)
    elseif suffix == "m" then mult = 1e6; s = s:sub(1,-2)
    elseif suffix == "b" then mult = 1e9; s = s:sub(1,-2)
    elseif suffix == "t" then mult = 1e12; s = s:sub(1,-2)
    elseif suffix == "q" then mult = 1e15; s = s:sub(1,-2) end
    local n = tonumber(s)
    return n and n * mult or nil
end

local function DecompileWithTimeout(module, timeout)
    if typeof(decompile) ~= "function" then return nil end
    local finished, okResult, result = false, false, nil
    task.spawn(function()
        local ok, value = pcall(decompile, module)
        okResult, result, finished = ok, value, true
    end)
    local start = os.clock()
    while not finished and not State.Dead and os.clock() - start < timeout do task.wait(.05) end
    if finished and okResult and typeof(result) == "string" then return result end
    return nil
end

local function FindEntryKey(source, displayStart, fallback)
    local prefix = source:sub(math.max(1, displayStart - 450), displayStart - 1)
    local bestPos, bestKey = -1, nil
    for pos, key in prefix:gmatch('()%["([^"]+)"%]%s*=%s*{') do
        if pos > bestPos then bestPos, bestKey = pos, key end
    end
    for pos, key in prefix:gmatch("()([%a_][%w_]*)%s*=%s*{") do
        if pos > bestPos then bestPos, bestKey = pos, key end
    end
    return bestKey or fallback
end

local function ParseAnimals(source)
    local db, names, seen = {}, {}, {}
    local pos, count = 1, 0
    while not State.Dead do
        local s, e, name = source:find('DisplayName%s*=%s*"([^"]+)"', pos)
        if not s then break end
        local nextDisplay = source:find('DisplayName%s*=%s*"', e + 1)
        local chunk = source:sub(s, nextDisplay and nextDisplay - 1 or math.min(#source, e + 1600))
        local key = FindEntryKey(source, s, name)
        local data = {
            Name = name,
            InternalKey = key,
            Rarity = chunk:match('Rarity%s*=%s*"([^"]+)"'),
            Price = tonumber(chunk:match("Price%s*=%s*([%d%.eE%-]+)") or ""),
            Generation = tonumber(chunk:match("Generation%s*=%s*([%d%.eE%-]+)") or ""),
        }
        db[name] = data
        if key then db[key] = data end
        if not seen[name] then seen[name] = true; names[#names+1] = name end
        count += 1
        if count % PARSE_YIELD_EVERY == 0 then task.wait() end
        pos = e + 1
    end
    table.sort(names, function(a,b)
        local ga = db[a] and db[a].Generation or 0
        local gb = db[b] and db[b].Generation or 0
        if ga ~= gb then return ga > gb end
        return a < b
    end)
    return db, names
end

local function NormalizeMutationName(v)
    if v == nil then return "" end
    return tostring(v):lower():gsub("[^%w]", "")
end

local function ParseMutations(source)
    local normal = { Key="Normal", DisplayText="Normal", Modifier=0 }
    local db = { Normal=normal, normal=normal }
    local names = { "Normal" }
    local pos, count = 1, 0
    while not State.Dead do
        local s,e,display = source:find('DisplayText%s*=%s*"([^"]+)"', pos)
        if not s then break end
        local nextDisplay = source:find('DisplayText%s*=%s*"', e + 1)
        local chunk = source:sub(s, nextDisplay and nextDisplay - 1 or math.min(#source,e+1300))
        local key = FindEntryKey(source,s,display)
        local data = { Key=key, DisplayText=display, Modifier=tonumber(chunk:match("Modifier%s*=%s*([%d%.eE%-]+)") or "") or 0 }
        db[key] = data
        db[display] = data
        db[NormalizeMutationName(key)] = data
        db[NormalizeMutationName(display)] = data
        names[#names+1] = display
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
    if UpdateDatabaseStatus then UpdateDatabaseStatus("Reading live Animals + Mutations...") end
    local datas = ReplicatedStorage:FindFirstChild("Datas")
    local animals = datas and datas:FindFirstChild("Animals")
    local mutations = datas and datas:FindFirstChild("Mutations")
    local animalSource = animals and DecompileWithTimeout(animals,10)
    local mutationSource = mutations and DecompileWithTimeout(mutations,10)
    if animalSource then
        local db,names = ParseAnimals(animalSource)
        if next(db) then GameData.Animals,GameData.AnimalNames = db,names end
    end
    if mutationSource then
        local db,names = ParseMutations(mutationSource)
        if next(db) then GameData.Mutations,GameData.MutationNames = db,names end
    end
    GameData.Ready = #GameData.AnimalNames > 0
    GameData.Refreshing = false
    GameData.LastRefresh = os.clock()
    if UpdateDatabaseStatus then
        UpdateDatabaseStatus(GameData.Ready and ("Ready | "..#GameData.AnimalNames.." Brainrots | "..#GameData.MutationNames.." mutations") or "Live database failed")
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
    return base * (1 + (m and m.Modifier or 0))
end
local function GetMutationMultiplier(mutation)
    local m = GetMutationData(mutation)
    return 1 + (m and m.Modifier or 0)
end
local function MatchMutationValue(value)
    local d = GameData.Mutations[NormalizeMutationName(value)]
    if d and d.DisplayText ~= "Normal" then return d.DisplayText end
    return nil
end
local function DetectMutation(model)
    if not model then return "Normal" end
    local descendants = model:GetDescendants()
    local objects = { model }
    local root = model:FindFirstChild("RootPart")
    if root then objects[#objects+1] = root end
    for _,d in ipairs(descendants) do objects[#objects+1] = d end
    for _,obj in ipairs(objects) do
        for key,value in pairs(obj:GetAttributes()) do
            if tostring(key):lower():find("mutation",1,true) then
                local found = MatchMutationValue(value); if found then return found end
            end
            if value == true then local found=MatchMutationValue(key);if found then return found end end
            if typeof(value)=="string" then local found=MatchMutationValue(value);if found then return found end end
        end
    end
    for _,d in ipairs(descendants) do
        if d:IsA("StringValue") then local found=MatchMutationValue(d.Value);if found then return found end end
        local found=MatchMutationValue(d.Name);if found then return found end
    end
    return "Normal"
end

local function InstancePosition(obj)
    if not obj then return nil end
    if obj:IsA("Attachment") then return obj.WorldPosition end
    if obj:IsA("BasePart") then return obj.Position end
    if obj:IsA("Model") then
        local ok,cf=pcall(obj.GetPivot,obj)
        if ok then return cf.Position end
        local p=obj:FindFirstChildWhichIsA("BasePart",true)
        return p and p.Position
    end
    local p=obj.Parent
    if p and p:IsA("Attachment") then return p.WorldPosition end
    if p and p:IsA("BasePart") then return p.Position end
    return nil
end

local function FaceTarget(pos)
    if not Root or not pos then return end
    local flat=Vector3.new(pos.X,Root.Position.Y,pos.Z)
    if (flat-Root.Position).Magnitude>.01 then pcall(function() Root.CFrame=CFrame.lookAt(Root.Position,flat) end) end
end

local cameraAimToken = 0
local function AimCameraFor(target, duration)
    cameraAimToken += 1
    local token = cameraAimToken
    task.spawn(function()
        local untilTime=os.clock()+(duration or .4)
        while token==cameraAimToken and not State.Dead and os.clock()<untilTime do
            local cam=workspace.CurrentCamera
            local pos=typeof(target)=="function" and target() or (typeof(target)=="Vector3" and target or InstancePosition(target))
            if cam and pos then pcall(function() cam.CFrame=CFrame.lookAt(cam.CFrame.Position,pos) end) end
            RunService.RenderStepped:Wait()
        end
    end)
end

local PromptBusy=setmetatable({}, {__mode="k"})
local function FirePromptOnce(prompt)
    if not prompt or not prompt.Parent or not prompt.Enabled then return false end
    if typeof(fireproximityprompt)~="function" or PromptBusy[prompt] then return false end
    PromptBusy[prompt]=true
    local hold=tonumber(prompt.HoldDuration) or 0
    local pos=InstancePosition(prompt)
    if pos then FaceTarget(pos); AimCameraFor(prompt,math.max(.4,hold+.35)) end
    local ok=pcall(function() fireproximityprompt(prompt) end)
    task.delay(math.max(hold,.05)+.22,function() PromptBusy[prompt]=nil end)
    return ok
end

local function GetBuyPrompt(model)
    local root=model and model:FindFirstChild("RootPart")
    local att=root and root:FindFirstChild("PromptAttachment")
    return att and att:FindFirstChildWhichIsA("ProximityPrompt") or nil
end
local function IsResultVisible(model)
    if not model or not model.Parent or not model:IsA("Model") then return false end
    local root=model:FindFirstChild("RootPart")
    return root and (root.Position-BUY_POSITION).Magnitude<ACTIVE_RANGE or false
end
local function GetActiveBrainrot()
    local folder=workspace:FindFirstChild("RNGMachineDisplay")
    if not folder then return nil end
    local best,bestD=nil,math.huge
    for _,model in ipairs(folder:GetChildren()) do
        local root=model:IsA("Model") and model:FindFirstChild("RootPart")
        if root then
            local d=(root.Position-BUY_POSITION).Magnitude
            if d<ACTIVE_RANGE and d<bestD then best,bestD=model,d end
        end
    end
    return best
end

local function FlatDistance(a,b)
    local dx,dz=a.X-b.X,a.Z-b.Z
    return math.sqrt(dx*dx+dz*dz)
end
local function MoveDirect(pos,timeout)
    Humanoid:MoveTo(pos)
    local started=os.clock()
    while State.Running and not State.Dead do
        if FlatDistance(Root.Position,pos)<=ARRIVAL_DISTANCE then return true end
        if os.clock()-started>(timeout or 3) then return false end
        task.wait(.05)
    end
    return false
end
local function ComputePath(pos)
    local path=PathfindingService:CreatePath({AgentRadius=2,AgentHeight=5,AgentCanJump=true,AgentJumpHeight=7,AgentMaxSlope=45})
    local ok=pcall(function() path:ComputeAsync(Root.Position,pos) end)
    if ok and path.Status==Enum.PathStatus.Success then return path:GetWaypoints() end
end
local function MoveAdaptive(pos,maxAttempts)
    if not State.Running or State.Dead then return false end
    if not Root or not Root.Parent then LoadCharacter() end
    if FlatDistance(Root.Position,pos)<=ARRIVAL_DISTANCE then return true end
    maxAttempts=maxAttempts or 5
    for attempt=1,maxAttempts do
        local waypoints=ComputePath(pos)
        if waypoints then
            local failed=false
            for _,wp in ipairs(waypoints) do
                if not State.Running or State.Dead then return false end
                if wp.Action==Enum.PathWaypointAction.Jump then Humanoid.Jump=true end
                Humanoid:MoveTo(wp.Position)
                local start=os.clock();local last=Root.Position;local lastMoved=os.clock()
                while State.Running and not State.Dead and FlatDistance(Root.Position,wp.Position)>ARRIVAL_DISTANCE do
                    if (Root.Position-last).Magnitude>.55 then last=Root.Position;lastMoved=os.clock()
                    elseif os.clock()-lastMoved>.85 then failed=true;break end
                    if os.clock()-start>2.8 then failed=true;break end
                    task.wait(.04)
                end
                if failed then break end
            end
            if not failed and FlatDistance(Root.Position,pos)<=6 then return true end
        elseif MoveDirect(pos,1.3) then return true end

        -- stuck: jump + alternate side + fresh path
        Humanoid.Jump=true
        local side=(attempt%2==0) and -1 or 1
        local sidestep=Root.Position+Root.CFrame.RightVector*(3.5*side)+Root.CFrame.LookVector*1.2
        Humanoid:MoveTo(sidestep)
        task.wait(.32)
    end
    return MoveDirect(pos,2.5)
end

local function PrepareSpinner()
    State.Phase="RETURN_START"
    if not MoveAdaptive(SPIN_POSITION,5) then return false end
    local p=InstancePosition(SpinPrompt)
    if p then FaceTarget(p);AimCameraFor(SpinPrompt,.45) end
    task.wait(.1)
    return true
end

local function GetHoney() return workspace:FindFirstChild("Honey") end
local function CollectHoneyIfPresent()
    local honey=GetHoney()
    if not honey or not honey.Parent then return false end
    State.Phase="HONEY"
    local started=os.clock()
    while State.Running and not State.Dead and honey.Parent and os.clock()-started<HONEY_SAFETY_TIMEOUT do
        local hp=InstancePosition(honey)
        if not hp then break end
        FaceTarget(hp);AimCameraFor(hp,.35)
        MoveAdaptive(hp,5)
        if not honey.Parent then break end
        local prompt=honey:FindFirstChildWhichIsA("ProximityPrompt",true)
        if prompt and prompt.Enabled and not PromptBusy[prompt] then FirePromptOnce(prompt) end
        if FlatDistance(Root.Position,hp)<=5 then
            Humanoid.Jump=true
            Humanoid:MoveTo(hp)
            task.wait(.3)
        else task.wait(.12) end
        if workspace:FindFirstChild("Honey")~=honey then break end
    end
    return true
end

local function RequestFunction()
    if typeof(request)=="function" then return request end
    if typeof(http_request)=="function" then return http_request end
    if typeof(syn)=="table" and typeof(syn.request)=="function" then return syn.request end
end
local function SendWebhook(name,data,mutation,actual,reason)
    if not Settings.WebhookEnabled or Settings.WebhookURL=="" then return end
    local req=RequestFunction();if not req then return end
    local url,mention=Settings.WebhookURL,Settings.WebhookMention
    task.spawn(function()
        local desc="**Brainrot:** "..name.."\n**Mutation:** "..mutation.."\n**Rarity:** "..tostring(data and data.Rarity or "?").."\n**Income:** $"..FormatMoney(actual).."/s\n**Matched by:** "..reason
        if mutation~="Normal" then desc..="\n**Base:** $"..FormatMoney(data and data.Generation).."/s\n**Multiplier:** "..string.format("%.3gx",GetMutationMultiplier(mutation)) end
        local payload={embeds={{title="RNG Target Found",description=desc}}}
        if mention~="" then payload.content=mention end
        local ok,body=pcall(HttpService.JSONEncode,HttpService,payload)
        if ok then pcall(req,{Url=url,Method="POST",Headers={["Content-Type"]="application/json"},Body=body}) end
    end)
end

-- UI
local GUI=Instance.new("ScreenGui")
GUI.Name="SmileB_RNG_Final"
GUI.ResetOnSpawn=false
GUI.Parent=Player:WaitForChild("PlayerGui")
State.GUI=GUI
local WINDOW_WIDTH,WINDOW_HEIGHT,MINI_SIZE=420,590,58
local Frame=Instance.new("Frame",GUI)
Frame.Size=UDim2.fromOffset(WINDOW_WIDTH,WINDOW_HEIGHT)
Frame.Position=UDim2.fromOffset(Settings.WindowX,Settings.WindowY)
Frame.BackgroundColor3=Color3.fromRGB(22,22,27)
Frame.BorderSizePixel=0
Frame.ClipsDescendants=true
local FrameCorner=Instance.new("UICorner",Frame);FrameCorner.CornerRadius=UDim.new(0,12)
local TitleBar=Instance.new("Frame",Frame);TitleBar.Size=UDim2.new(1,0,0,44);TitleBar.BackgroundTransparency=1
local Title=Instance.new("TextLabel",TitleBar);Title.Size=UDim2.new(1,-100,1,0);Title.Position=UDim2.fromOffset(14,0);Title.BackgroundTransparency=1;Title.Text="RNG Auto Buyer";Title.TextXAlignment=Enum.TextXAlignment.Left;Title.Font=Enum.Font.GothamBold;Title.TextSize=16;Title.TextColor3=Color3.new(1,1,1)
local MinButton=Instance.new("TextButton",TitleBar);MinButton.Size=UDim2.fromOffset(38,30);MinButton.Position=UDim2.new(1,-47,0,7);MinButton.BackgroundColor3=Color3.fromRGB(42,42,48);MinButton.BorderSizePixel=0;MinButton.Text="−";MinButton.TextColor3=Color3.new(1,1,1);MinButton.TextSize=20
local Content=Instance.new("Frame",Frame);Content.Size=UDim2.new(1,-20,1,-54);Content.Position=UDim2.fromOffset(10,46);Content.BackgroundTransparency=1
local MiniButton=Instance.new("TextButton",Frame);MiniButton.Size=UDim2.fromScale(1,1);MiniButton.BackgroundTransparency=1;MiniButton.Text="🍯";MiniButton.TextColor3=Color3.new(1,1,1);MiniButton.TextSize=28;MiniButton.Font=Enum.Font.GothamBold;MiniButton.Visible=false

local function AttachDrag(handle,allowTap,tap)
    local dragging=false;local startMouse,startFrame,activeInput;local moved=false
    Track(handle.InputBegan:Connect(function(input)
        if input.UserInputType==Enum.UserInputType.MouseButton1 or input.UserInputType==Enum.UserInputType.Touch then dragging=true;moved=false;startMouse=input.Position;startFrame=Frame.Position;activeInput=input end
    end))
    Track(UserInputService.InputChanged:Connect(function(input)
        if not dragging then return end
        if input.UserInputType~=Enum.UserInputType.MouseMovement and input.UserInputType~=Enum.UserInputType.Touch then return end
        local delta=input.Position-startMouse;if delta.Magnitude>5 then moved=true end
        Frame.Position=UDim2.new(startFrame.X.Scale,startFrame.X.Offset+delta.X,startFrame.Y.Scale,startFrame.Y.Offset+delta.Y)
    end))
    Track(UserInputService.InputEnded:Connect(function(input)
        if dragging and (input==activeInput or input.UserInputType==Enum.UserInputType.MouseButton1 or input.UserInputType==Enum.UserInputType.Touch) then
            dragging=false;Settings.WindowX=Frame.Position.X.Offset;Settings.WindowY=Frame.Position.Y.Offset;QueueSave();if allowTap and not moved and tap then tap() end
        end
    end))
end

local Animating=false
local function OpenUI()
    if not State.Minimized or Animating then return end
    Animating=true;State.Minimized=false
    TweenService:Create(MiniButton,TweenInfo.new(.32,Enum.EasingStyle.Back),{Rotation=MiniButton.Rotation+360}):Play()
    local tw=TweenService:Create(Frame,TweenInfo.new(.28,Enum.EasingStyle.Quint),{Size=UDim2.fromOffset(WINDOW_WIDTH,WINDOW_HEIGHT)});tw:Play();tw.Completed:Wait()
    MiniButton.Visible=false;TitleBar.Visible=true;Content.Visible=true;Animating=false;QueueSave()
end
local function MinimizeUI()
    if State.Minimized or Animating then return end
    Animating=true;State.Minimized=true;TitleBar.Visible=false;Content.Visible=false;MiniButton.Visible=true;MiniButton.Rotation=0
    TweenService:Create(MiniButton,TweenInfo.new(.35,Enum.EasingStyle.Back),{Rotation=360}):Play()
    local tw=TweenService:Create(Frame,TweenInfo.new(.28,Enum.EasingStyle.Quint),{Size=UDim2.fromOffset(MINI_SIZE,MINI_SIZE)});tw:Play();tw.Completed:Wait();Animating=false;QueueSave()
end
Track(MinButton.MouseButton1Click:Connect(MinimizeUI));AttachDrag(TitleBar,false,nil);AttachDrag(MiniButton,true,OpenUI)

local function Label(y,h,text,size)
    local l=Instance.new("TextLabel",Content);l.Position=UDim2.fromOffset(0,y);l.Size=UDim2.new(1,0,0,h);l.BackgroundTransparency=1;l.Text=text;l.TextColor3=Color3.fromRGB(190,190,195);l.TextXAlignment=Enum.TextXAlignment.Left;l.Font=Enum.Font.Gotham;l.TextSize=size or 10;return l
end
local DatabaseStatus=Label(0,20,"Loading live data...",10)
UpdateDatabaseStatus=function(t) if DatabaseStatus.Parent then DatabaseStatus.Text=t end end
local Status=Label(21,22,"Ready",11)
local ResultLabel=Label(43,48,"Spins: 0\nNo result yet",11);ResultLabel.TextWrapped=true;ResultLabel.TextYAlignment=Enum.TextYAlignment.Top
local function SetStatus(t) if Status.Parent then Status.Text=t end end

local function Toggle(text,x,getter,setter)
    local b=Instance.new("TextButton",Content);b.Position=UDim2.fromOffset(x,96);b.Size=UDim2.fromOffset(x==266 and 134 or 125,32);b.BorderSizePixel=0;b.TextColor3=Color3.new(1,1,1);b.Font=Enum.Font.GothamBold;b.TextSize=10
    local function refresh() local on=getter();b.Text=text..": "..(on and "ON" or "OFF");b.BackgroundColor3=on and Color3.fromRGB(45,145,75) or Color3.fromRGB(72,72,80) end
    Track(b.MouseButton1Click:Connect(function() setter(not getter());refresh();QueueSave() end));refresh();return b
end
Toggle("NAME",0,function()return Settings.NameFilter end,function(v)Settings.NameFilter=v end)
Toggle("MONEY",133,function()return Settings.MoneyFilter end,function(v)Settings.MoneyFilter=v end)
Toggle("AUTO DATA",266,function()return Settings.AutoRefresh end,function(v)Settings.AutoRefresh=v end)

local MoneyInput=Instance.new("TextBox",Content);MoneyInput.Position=UDim2.fromOffset(0,135);MoneyInput.Size=UDim2.new(1,0,0,34);MoneyInput.BackgroundColor3=Color3.fromRGB(35,35,42);MoneyInput.BorderSizePixel=0;MoneyInput.TextColor3=Color3.new(1,1,1);MoneyInput.PlaceholderText="Minimum FINAL income >= e.g. 10M";MoneyInput.Text=tostring(Settings.MinGeneration);MoneyInput.ClearTextOnFocus=false;MoneyInput.Font=Enum.Font.Gotham;MoneyInput.TextSize=11
local function ApplyMoney() local v=ParseNumber(MoneyInput.Text);if v then Settings.MinGeneration=v;MoneyInput.Text=tostring(v);QueueSave() else MoneyInput.Text=tostring(Settings.MinGeneration) end end
Track(MoneyInput.FocusLost:Connect(ApplyMoney))

local Search=Instance.new("TextBox",Content);Search.Position=UDim2.fromOffset(0,177);Search.Size=UDim2.new(1,-100,0,32);Search.BackgroundColor3=Color3.fromRGB(35,35,42);Search.BorderSizePixel=0;Search.TextColor3=Color3.new(1,1,1);Search.PlaceholderText="Search Brainrots...";Search.Text="";Search.Font=Enum.Font.Gotham;Search.TextSize=11
local Clear=Instance.new("TextButton",Content);Clear.Position=UDim2.new(1,-92,0,177);Clear.Size=UDim2.fromOffset(92,32);Clear.Text="CLEAR";Clear.BackgroundColor3=Color3.fromRGB(65,65,73);Clear.TextColor3=Color3.new(1,1,1);Clear.BorderSizePixel=0;Clear.Font=Enum.Font.GothamBold;Clear.TextSize=10
local SelectedLabel=Label(211,18,"Selected: 0",10)
local function CountSelected() local n=0;for _,v in pairs(Settings.Selected)do if v then n+=1 end end;return n end
UpdateSelectedCount=function()SelectedLabel.Text="Selected Brainrots: "..CountSelected()end;UpdateSelectedCount()
local List=Instance.new("ScrollingFrame",Content);List.Position=UDim2.fromOffset(0,231);List.Size=UDim2.new(1,0,0,205);List.BackgroundColor3=Color3.fromRGB(29,29,35);List.BorderSizePixel=0;List.ScrollBarThickness=5
local Layout=Instance.new("UIListLayout",List);Layout.Padding=UDim.new(0,3)
local renderVersion=0
RenderDatabase=function()
    renderVersion+=1;local my=renderVersion
    for _,c in ipairs(List:GetChildren())do if c~=Layout then c:Destroy()end end
    local q=Search.Text:lower();local candidates={}
    for _,name in ipairs(GameData.AnimalNames)do if q=="" or name:lower():find(q,1,true) then candidates[#candidates+1]=name end end
    table.sort(candidates,function(a,b)
        local sa,sb=Settings.Selected[a]==true,Settings.Selected[b]==true;if sa~=sb then return sa end
        local ga=GetAnimalData(a) and GetAnimalData(a).Generation or 0;local gb=GetAnimalData(b) and GetAnimalData(b).Generation or 0
        if ga~=gb then return ga>gb end;return a<b
    end)
    local added=0
    for _,name in ipairs(candidates)do
        if my~=renderVersion then return end
        local data=GetAnimalData(name);local b=Instance.new("TextButton",List);b.Size=UDim2.new(1,-7,0,30);b.BorderSizePixel=0;b.TextXAlignment=Enum.TextXAlignment.Left;b.Font=Enum.Font.Gotham;b.TextSize=10;b.TextColor3=Color3.new(1,1,1)
        local function row() local sel=Settings.Selected[name]==true;b.BackgroundColor3=sel and Color3.fromRGB(40,110,65) or Color3.fromRGB(42,42,49);b.Text=(sel and "  ✓ " or "    ")..name.." | "..tostring(data and data.Rarity or "?").." | $"..FormatMoney(data and data.Generation).."/s" end
        row();Track(b.MouseButton1Click:Connect(function() if Settings.Selected[name] then Settings.Selected[name]=nil else Settings.Selected[name]=true end;UpdateSelectedCount();QueueSave();RenderDatabase() end))
        added+=1;if added>=MAX_VISIBLE_ROWS then break end
    end
    task.defer(function()if List.Parent then List.CanvasSize=UDim2.fromOffset(0,Layout.AbsoluteContentSize.Y+5)end end)
end
local searchToken=0
Track(Search:GetPropertyChangedSignal("Text"):Connect(function()searchToken+=1;local t=searchToken;task.delay(.12,function()if t==searchToken and not State.Dead then RenderDatabase()end end)end))
Track(Clear.MouseButton1Click:Connect(function()Settings.Selected={};UpdateSelectedCount();RenderDatabase();QueueSave()end))

local WebToggle=Toggle("WEBHOOK",0,function()return Settings.WebhookEnabled end,function(v)Settings.WebhookEnabled=v end);WebToggle.Position=UDim2.fromOffset(0,444)
local WebhookInput=Instance.new("TextBox",Content);WebhookInput.Position=UDim2.fromOffset(113,444);WebhookInput.Size=UDim2.new(1,-113,0,32);WebhookInput.BackgroundColor3=Color3.fromRGB(35,35,42);WebhookInput.BorderSizePixel=0;WebhookInput.TextColor3=Color3.new(1,1,1);WebhookInput.PlaceholderText="Discord webhook URL";WebhookInput.Text=Settings.WebhookURL;WebhookInput.ClearTextOnFocus=false;WebhookInput.Font=Enum.Font.Gotham;WebhookInput.TextSize=9
Track(WebhookInput.FocusLost:Connect(function()Settings.WebhookURL=WebhookInput.Text;QueueSave()end))
local Mention=Instance.new("TextBox",Content);Mention.Position=UDim2.fromOffset(0,484);Mention.Size=UDim2.new(1,-120,0,32);Mention.BackgroundColor3=Color3.fromRGB(35,35,42);Mention.BorderSizePixel=0;Mention.TextColor3=Color3.new(1,1,1);Mention.PlaceholderText="Optional ping: <@DiscordUserID>";Mention.Text=Settings.WebhookMention;Mention.ClearTextOnFocus=false;Mention.Font=Enum.Font.Gotham;Mention.TextSize=9
Track(Mention.FocusLost:Connect(function()Settings.WebhookMention=Mention.Text;QueueSave()end))
local StartButton=Instance.new("TextButton",Content);StartButton.Position=UDim2.new(1,-112,0,484);StartButton.Size=UDim2.fromOffset(112,32);StartButton.BackgroundColor3=Color3.fromRGB(45,155,78);StartButton.BorderSizePixel=0;StartButton.Text="START";StartButton.TextColor3=Color3.new(1,1,1);StartButton.Font=Enum.Font.GothamBold;StartButton.TextSize=11

function State.Cleanup()
    State.Running=false;State.Dead=true;SaveNow();cameraAimToken+=1
    for _,c in ipairs(State.Connections)do pcall(function()c:Disconnect()end)end
    table.clear(State.Connections)
    if State.GUI then pcall(function()State.GUI:Destroy()end)end
    if ENV[SCRIPT_KEY]==State then ENV[SCRIPT_KEY]=nil end
end
Track(Player.CharacterAdded:Connect(function()task.wait(.7);if not State.Dead then LoadCharacter()end end))

local function ShouldBuy(model,mutation)
    local data=GetAnimalData(model.Name)
    local actual=GetEffectiveGeneration(data and data.Generation,mutation)
    local nameMatch=false;local moneyMatch=false
    if Settings.NameFilter then
        nameMatch=Settings.Selected[model.Name]==true
        if not nameMatch and data and data.Name then nameMatch=Settings.Selected[data.Name]==true end
    end
    if Settings.MoneyFilter and actual then moneyMatch=actual>=Settings.MinGeneration end
    return nameMatch or moneyMatch,data,nameMatch,moneyMatch,actual
end

-- Detect the next result, but DO NOT move toward it and DO NOT evaluate/buy yet.
-- The caller must wait for WaitUntilResultReady first.
local function SpinAndDetectNewResult()
    if not PrepareSpinner() then return nil end
    State.Phase="SPINNING"

    local old=GetActiveBrainrot()
    local oldPrompt=GetBuyPrompt(old)
    local sawGap=(old==nil)
    local oldPromptRemoved=false
    local temp={}
    if old and old:FindFirstChild("RootPart") then
        temp[#temp+1]=old.RootPart.ChildRemoved:Connect(function(child) if child.Name=="PromptAttachment" then oldPromptRemoved=true end end)
    end
    if oldPrompt then
        temp[#temp+1]=oldPrompt.AncestryChanged:Connect(function(_,parent) if not parent then oldPromptRemoved=true end end)
    end

    local p=InstancePosition(SpinPrompt)
    if p then FaceTarget(p);AimCameraFor(SpinPrompt,math.max(.6,(SpinPrompt.HoldDuration or 0)+.4)) end
    if not FirePromptOnce(SpinPrompt) then
        for _,c in ipairs(temp)do c:Disconnect()end
        return nil
    end

    local started=os.clock()
    local result=nil
    while State.Running and not State.Dead and os.clock()-started<SPIN_TRANSITION_TIMEOUT do
        if old and not IsResultVisible(old) then sawGap=true end
        local current=GetActiveBrainrot()
        if current then
            if not old then result=current;break end
            if current~=old then result=current;break end
            if current==old and sawGap then result=current;break end
            -- same preloaded model can repeat; a newly-created buy prompt is proof of a new cycle
            local cp=GetBuyPrompt(current)
            if current==old and oldPromptRemoved and cp and cp~=oldPrompt then result=current;break end
        end
        task.wait(SCAN_INTERVAL)
    end
    for _,c in ipairs(temp)do pcall(function()c:Disconnect()end)end
    return result
end

-- CRITICAL FIX: stay at the spinner while the RNG animation plays.
-- A result is not considered ready until its PromptAttachment/ProximityPrompt exists and is enabled.
local function WaitUntilResultReady(model)
    if not model then return nil end
    State.Phase="WAIT_RESULT_READY"
    SetStatus("Result animation... waiting until BUY appears")
    local started=os.clock()
    while State.Running and not State.Dead and os.clock()-started<RESULT_READY_TIMEOUT do
        local prompt=GetBuyPrompt(model)
        if prompt and prompt.Parent and prompt.Enabled then
            -- small settle margin so we do not move on the exact frame it appears
            task.wait(.12)
            if GetBuyPrompt(model)==prompt and prompt.Parent and prompt.Enabled then return prompt end
        end
        -- Do not move toward the Brainrot here. Keep facing the machine.
        local sp=InstancePosition(SpinPrompt)
        if sp then FaceTarget(sp);AimCameraFor(SpinPrompt,.15) end
        task.wait(.035)
    end
    return nil
end

-- Once we decide to buy, no code path can call the spin prompt until this returns.
local function BuyLocked(model)
    State.Phase="BUY_LOCK"
    SetStatus("TARGET LOCKED | moving only after BUY prompt is ready")
    local readyPrompt=GetBuyPrompt(model)
    if not readyPrompt then return false end

    if not MoveAdaptive(BUY_POSITION,6) then
        SetStatus("Buy path failed | retrying position")
        MoveAdaptive(BUY_POSITION,6)
    end

    local started=os.clock();local attempts=0
    while State.Running and not State.Dead and os.clock()-started<BUY_SAFETY_TIMEOUT do
        local prompt=GetBuyPrompt(model)
        local visible=IsResultVisible(model)
        if not visible and not prompt then
            SetStatus("Target handled / disappeared")
            return true
        end
        if prompt and prompt.Enabled then
            local pp=InstancePosition(prompt)
            if pp then FaceTarget(pp);AimCameraFor(prompt,math.max(.45,(prompt.HoldDuration or 0)+.3)) end
            if not PromptBusy[prompt] and FirePromptOnce(prompt) then
                attempts+=1
                -- Wait for this hold attempt to finish before another attempt.
                local waitUntil=os.clock()+math.max(prompt.HoldDuration or 0,.05)+.24
                while State.Running and not State.Dead and os.clock()<waitUntil do
                    if not IsResultVisible(model) and not GetBuyPrompt(model) then return true end
                    task.wait(.025)
                end
            end
        else
            -- Do NOT spin just because the prompt temporarily vanished. A matched result keeps the lock.
            task.wait(.04)
        end
    end
    SetStatus("Target buy lock ended after "..attempts.." attempts")
    return false
end

local Spins=0
local function HandleHoneyAndReturn()
    -- Called only after the current RNG result is fully handled.
    if GetHoney() then
        SetStatus("Honey found | RNG paused")
        CollectHoneyIfPresent()
    end
    if State.Running then
        SetStatus("Returning to start position...")
        PrepareSpinner()
    end
end

local function MainLoop()
    if State.LoopRunning then return end
    State.LoopRunning=true
    while State.Running and not State.Dead and not GameData.Ready do SetStatus("Waiting for live database...");task.wait(.1) end
    if not State.Running or State.Dead then State.LoopRunning=false;return end

    -- Honey existing before the first spin is safe to collect now.
    HandleHoneyAndReturn()

    while State.Running and not State.Dead do
        -- Every cycle begins at SPIN_POSITION, facing the spin prompt.
        if not PrepareSpinner() then SetStatus("Can't reach start | retrying");task.wait(.2);continue end
        SetStatus("Spinning once...")

        local current=SpinAndDetectNewResult()
        if not current then
            SetStatus("No new result detected | retrying from start")
            task.wait(.15)
            continue
        end

        -- Absolutely no movement toward BUY_POSITION while animation is running.
        local buyPrompt=WaitUntilResultReady(current)
        if not buyPrompt then
            -- We never spin over a result while it is mid-animation. If readiness timed out,
            -- wait for the result to leave or become ready before allowing another spin.
            SetStatus("Result not ready yet | holding spin lock")
            local lockStart=os.clock()
            while State.Running and not State.Dead and os.clock()-lockStart<8 do
                buyPrompt=GetBuyPrompt(current)
                if buyPrompt and buyPrompt.Enabled then break end
                if not IsResultVisible(current) then break end
                task.wait(.05)
            end
            if not buyPrompt or not buyPrompt.Enabled then
                HandleHoneyAndReturn()
                continue
            end
        end

        -- The animation is now finished. Count/evaluate exactly once here.
        Spins+=1
        local mutation=DetectMutation(current)
        local buy,data,nameMatch,moneyMatch,actual=ShouldBuy(current,mutation)
        local rarity=data and data.Rarity or "?"
        ResultLabel.Text="Spins: "..Spins.."\n"..current.Name.." | "..mutation.." | "..rarity.." | $"..FormatMoney(actual).."/s"..(mutation~="Normal" and (" | "..string.format("%.3gx",GetMutationMultiplier(mutation))) or "")
        print("[SmileB RNG] READY RESULT",Spins,current.Name,"income",actual,"nameMatch",nameMatch,"moneyMatch",moneyMatch)

        -- User requested being back at the start after each spin. We stayed there during animation,
        -- but enforce it again in case Roblox pushed the character.
        if FlatDistance(Root.Position,SPIN_POSITION)>ARRIVAL_DISTANCE then MoveAdaptive(SPIN_POSITION,4) end

        if buy then
            local reason=(nameMatch and moneyMatch) and "Name + Money" or (nameMatch and "Name" or "Money")
            SetStatus("FOUND "..reason.." | BUY LOCK ON")
            SendWebhook(current.Name,data,mutation,actual,reason)

            -- Buying ALWAYS wins over Honey and over the next spin.
            BuyLocked(current)

            -- Honey can only interrupt after the buying section has completed.
            HandleHoneyAndReturn()
        else
            SetStatus("Not targeted | result finished")
            -- Honey is checked between completed spins, never during an animation.
            HandleHoneyAndReturn()
        end
    end

    State.LoopRunning=false
    if not State.Dead then SetStatus("Stopped") end
end

Track(StartButton.MouseButton1Click:Connect(function()
    ApplyMoney();Settings.WebhookURL=WebhookInput.Text;Settings.WebhookMention=Mention.Text;QueueSave()
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
if Settings.Minimized then task.defer(function()task.wait(.15);if not State.Dead and not State.Minimized then MinimizeUI()end end)end

print("[SmileB RNG] Loaded",VERSION)
print("[SmileB RNG] Result-ready lock enabled: no buying/moving during animation, no respin before target handling")
