from pathlib import Path
import re

TARGET = Path('99 Nights Helper Godmode')
s = TARGET.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global s
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly 1 match, got {count}')
    s = s.replace(old, new, 1)


def insert_before(anchor, block, label):
    global s
    count = s.count(anchor)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly 1 anchor, got {count}')
    s = s.replace(anchor, block + anchor, 1)

# ---------------------------------------------------------------------------
# Remote discovery + state
# ---------------------------------------------------------------------------
replace_once(
    'local RequestPlaceStructure = nil',
    '''local RequestPlaceStructure = nil
local RequestOpenItemChest = nil
local RequestTakeDiamonds = nil''',
    'stronghold remote declarations'
)

replace_once(
    '    RequestPlaceStructure = findReplicated("RequestPlaceStructure")',
    '''    RequestPlaceStructure = findReplicated("RequestPlaceStructure")
    RequestOpenItemChest = findReplicated("RequestOpenItemChest")
    RequestTakeDiamonds = findReplicated("RequestTakeDiamonds")''',
    'stronghold remote refresh'
)

replace_once(
    '''        or name == "RequestBagStoreItem"
        or name == "RequestBagDropItem" then''',
    '''        or name == "RequestBagStoreItem"
        or name == "RequestBagDropItem"
        or name == "RequestPlantItem"
        or name == "CraftItem"
        or name == "RequestPlaceStructure"
        or name == "RequestOpenItemChest"
        or name == "RequestTakeDiamonds" then''',
    'descendant remote refresh list'
)

replace_once(
    '''    autoBestGear = false,
    autoFarm = false,
    smartResources = false,''',
    '''    autoBestGear = false,
    autoFarm = false,
    smartResources = false,
    autoPlant = false,
    autoCampBuild = false,
    autoChest = false,
    autoChildRescue = false,
    diamondFarm = false,

    strongholdControl = false,
    strongholdRunning = false,
    strongholdCycleComplete = false,
    strongholdStatus = "Off",
    strongholdCountdown = "--",
    strongholdBaseline = nil,
    diamondScriptStart = nil,
    strongholdLastGain = 0,
    strongholdRetryAt = 0,
    strongholdManualKillRestore = nil,''',
    'automation state'
)

replace_once(
    '''    previousState.saplingServiceRunning = false
    previousState.campBuildRunning = false''',
    '''    previousState.saplingServiceRunning = false
    previousState.campBuildRunning = false
    previousState.autoPlant = false
    previousState.autoCampBuild = false
    previousState.autoChest = false
    previousState.autoChildRescue = false
    previousState.diamondFarm = false
    previousState.strongholdControl = false
    previousState.strongholdRunning = false''',
    'previous state cleanup'
)

# ---------------------------------------------------------------------------
# Stronghold/Diamond controller. Insert after instant chest helpers exist.
# ---------------------------------------------------------------------------
stronghold_block = r'''

--==============================================================
-- STRONGHOLD / VERIFIED DIAMOND FARM
--==============================================================

local function parseCountText(value)
    if type(value) == "number" then
        return math.max(0, math.floor(value + 0.0001))
    end
    if type(value) ~= "string" then
        return nil
    end

    local compact = string.gsub(value, "[, %s]", "")
    local direct = tonumber(compact)
    if direct ~= nil then
        return math.max(0, math.floor(direct + 0.0001))
    end

    local number, suffix = string.match(string.lower(compact), "([%d%.]+)([kmbt])")
    number = tonumber(number)
    if not number then
        return nil
    end
    local multipliers = { k = 1e3, m = 1e6, b = 1e9, t = 1e12 }
    return math.max(0, math.floor(number * (multipliers[suffix] or 1) + 0.5))
end

local function getDiamondCount()
    for _, attributeName in ipairs({ "Diamonds", "DiamondCount", "Diamond" }) do
        local value = player:GetAttribute(attributeName)
        local parsed = parseCountText(value)
        if parsed ~= nil then
            return parsed
        end
    end

    local interface = playerGui:FindFirstChild("Interface")
    local diamondCount = interface and interface:FindFirstChild("DiamondCount")
    local countObject = diamondCount and diamondCount:FindFirstChild("Count")
    if countObject then
        local ok, value = pcall(function()
            return countObject.Text
        end)
        if ok then
            local parsed = parseCountText(value)
            if parsed ~= nil then
                return parsed
            end
        end
        local okValue, value = pcall(function()
            return countObject.Value
        end)
        if okValue then
            local parsed = parseCountText(value)
            if parsed ~= nil then
                return parsed
            end
        end
    end

    return nil
end

state.diamondScriptStart = getDiamondCount()

local function getStrongholdFunctional()
    local map = workspace:FindFirstChild("Map")
    local landmarks = map and map:FindFirstChild("Landmarks")
    local stronghold = landmarks and landmarks:FindFirstChild("Stronghold")
    return stronghold and stronghold:FindFirstChild("Functional")
end

local function getStrongholdCountdownText()
    local functional = getStrongholdFunctional()
    if not functional then
        return "Missing"
    end

    local sign = functional:FindFirstChild("Sign")
    local body = sign and sign:FindFirstChild("Body", true)
    if body then
        local ok, text = pcall(function()
            return body.Text
        end)
        if ok and type(text) == "string" and text ~= "" then
            return text
        end
    end
    return "Waiting"
end

local function strongholdDoorOpen()
    local functional = getStrongholdFunctional()
    local entryDoors = functional and functional:FindFirstChild("EntryDoors")
    return entryDoors and entryDoors:GetAttribute("DoorOpen") == true or false
end

local function strongholdGateOpen()
    local functional = getStrongholdFunctional()
    local finalGate = functional and functional:FindFirstChild("FinalGate")
    if not finalGate then
        return false
    end

    local original = finalGate:GetAttribute("OriginalCF")
    if typeof(original) == "CFrame" then
        local ok, pivot = pcall(function()
            return finalGate:GetPivot()
        end)
        if ok and (pivot.Position - original.Position).Magnitude > 1 then
            return true
        end
    end

    for _, attributeName in ipairs({ "Open", "Opened", "DoorOpen", "Unlocked" }) do
        if finalGate:GetAttribute(attributeName) == true then
            return true
        end
    end
    return false
end

local function getStrongholdChest()
    local items = workspace:FindFirstChild("Items")
    return items and items:FindFirstChild("Stronghold Diamond Chest")
end

local function strongholdChestOpened(chest)
    if not chest then
        return false
    end
    if chest:GetAttribute("LocalOpened") == true then
        return true
    end
    if chest:GetAttribute(tostring(player.UserId) .. "Opened") == true then
        return true
    end
    return false
end

local function strongholdReady()
    local countdown = getStrongholdCountdownText()
    local normalized = string.lower(string.gsub(countdown, "%s+", ""))
    if normalized == "00s" or normalized == "0s" or normalized == "ready" then
        return true
    end
    if strongholdDoorOpen() or strongholdGateOpen() then
        return true
    end

    local functional = getStrongholdFunctional()
    local entry = functional and functional:FindFirstChild("EntryDoors")
    if entry then
        local prompt = entry:FindFirstChildWhichIsA("ProximityPrompt", true)
        if prompt and prompt.Enabled then
            return true
        end
    end
    return false
end

local function releaseFarmForStronghold()
    cancelFarmTween()
    local root = getRoot()
    if root and root.Parent then
        pcall(function()
            root.Anchored = false
            root.AssemblyLinearVelocity = Vector3.zero
            root.AssemblyAngularVelocity = Vector3.zero
        end)
    end
end

local function strongholdPivot(target, offset)
    local character = getCharacter()
    if not character or not target then
        return false
    end

    local cf = nil
    if typeof(target) == "CFrame" then
        cf = target
    elseif typeof(target) == "Vector3" then
        cf = CFrame.new(target)
    elseif typeof(target) == "Instance" then
        if target:IsA("BasePart") then
            cf = target.CFrame
        elseif target:IsA("Model") then
            local ok, pivot = pcall(target.GetPivot, target)
            if ok then cf = pivot end
        end
    end
    if not cf then
        return false
    end

    local delta = offset or Vector3.new(0, 3, 0)
    releaseFarmForStronghold()
    local ok = pcall(character.PivotTo, character, cf + delta)
    if ok then
        task.wait(0.2)
    end
    return ok
end

local function touchStrongholdZone(zone)
    if not zone or not zone.Parent then
        return false
    end
    strongholdPivot(zone, Vector3.new(0, 3, 0))

    local root = getRoot()
    local fireTouch = rawget(G, "firetouchinterest")
    if type(fireTouch) ~= "function" and type(firetouchinterest) == "function" then
        fireTouch = firetouchinterest
    end
    if root and type(fireTouch) == "function" then
        local began = pcall(fireTouch, root, zone, 0)
        task.wait(0.06)
        pcall(fireTouch, root, zone, 1)
        return began
    end

    if root then
        pcall(function()
            root.CFrame = zone.CFrame * CFrame.new(0, 0.5, 0)
        end)
        task.wait(0.15)
        return true
    end
    return false
end

local function activateStrongholdPrompts()
    local functional = getStrongholdFunctional()
    if not functional then
        return 0
    end

    local fired = 0
    for _, object in ipairs(functional:GetDescendants()) do
        if not state.diamondFarm or not state.strongholdControl then
            break
        end
        if object:IsA("ProximityPrompt") and object.Enabled then
            local part = getPromptPart(object)
            if part then
                strongholdPivot(part, Vector3.new(0, 3, 0))
            end
            if firePromptNow(object) then
                fired = fired + 1
            end
            task.wait(0.08)
            if fired >= 12 then
                break
            end
        end
    end
    return fired
end

local function activateStrongholdWaves()
    local functional = getStrongholdFunctional()
    if not functional then
        return 0
    end

    local zones = {}
    for _, object in ipairs(functional:GetDescendants()) do
        if object:IsA("BasePart") and object.Name == "TriggerZone" then
            table.insert(zones, object)
        end
    end
    table.sort(zones, function(a, b)
        return a:GetFullName() < b:GetFullName()
    end)

    local touched = 0
    for _, zone in ipairs(zones) do
        if not state.diamondFarm or not state.strongholdControl then
            break
        end
        if touchStrongholdZone(zone) then
            touched = touched + 1
        end
        task.wait(0.12)
    end
    return touched
end

local function collectStrongholdDiamonds()
    if not isLive(RequestTakeDiamonds) then
        refreshRemotes()
    end
    if not isLive(RequestTakeDiamonds) then
        return 0
    end

    local items = workspace:FindFirstChild("Items")
    if not items then
        return 0
    end

    local requested = 0
    for _, object in ipairs(items:GetDescendants()) do
        if object.Name == "Diamond" and (object:IsA("Model") or object:IsA("BasePart")) then
            local ok = callUtilityRemote(RequestTakeDiamonds, 0.75, object)
            if ok then
                requested = requested + 1
            end
        end
    end
    return requested
end

local function openStrongholdDiamondChest(chest)
    if not chest or not chest.Parent then
        return false
    end

    strongholdPivot(chest, Vector3.new(0, 3, 0))
    local prompt = chest:FindFirstChildWhichIsA("ProximityPrompt", true)
    if prompt then
        for _ = 1, 4 do
            firePromptNow(prompt)
            task.wait(0.12)
        end
    end

    if not isLive(RequestOpenItemChest) then
        refreshRemotes()
    end
    if isLive(RequestOpenItemChest) then
        local ok, response = callUtilityRemote(RequestOpenItemChest, 1.5, chest)
        if ok and response ~= false then
            return true
        end
    end
    return prompt ~= nil
end

local function finishStrongholdControl(success)
    state.strongholdRunning = false
    if success then
        state.strongholdControl = false
        state.strongholdCycleComplete = true
        state.strongholdRetryAt = 0
        if not state.autoFarm and state.strongholdManualKillRestore ~= nil then
            state.killAura = state.strongholdManualKillRestore
        end
        state.strongholdManualKillRestore = nil
    else
        -- Never release Auto Farm to its under-map/night controller until a
        -- real diamond-count increase has been observed.
        state.strongholdControl = state.diamondFarm
        state.strongholdRetryAt = os.clock() + 3
    end
end

local function runStrongholdCycle()
    if not state.active or not state.diamondFarm or state.strongholdRunning then
        return false
    end

    local functional = getStrongholdFunctional()
    if not functional then
        state.strongholdStatus = "Stronghold not loaded"
        return false
    end

    local baseline = getDiamondCount()
    if baseline == nil then
        state.strongholdStatus = "Waiting for diamond count"
        state.strongholdControl = true
        state.strongholdRetryAt = os.clock() + 2
        return false
    end

    if state.diamondScriptStart == nil then
        state.diamondScriptStart = baseline
    end

    state.strongholdBaseline = baseline
    state.strongholdControl = true
    state.strongholdRunning = true
    state.strongholdStatus = "Entering stronghold"
    if not state.autoFarm and state.strongholdManualKillRestore == nil then
        state.strongholdManualKillRestore = state.killAura
    end
    state.killAura = true
    releaseFarmForStronghold()

    local ok = pcall(function()
        local strongholdModel = functional.Parent
        if strongholdModel then
            strongholdPivot(strongholdModel, Vector3.new(0, 5, 0))
        end

        activateStrongholdPrompts()
        activateStrongholdWaves()

        local fightDeadline = os.clock() + 120
        local nextTriggerAt = 0
        while state.active and state.diamondFarm and state.strongholdControl do
            state.killAura = true
            if strongholdGateOpen() then
                break
            end

            local chest = getStrongholdChest()
            if chest and strongholdChestOpened(chest) then
                break
            end

            local now = os.clock()
            if now >= nextTriggerAt then
                state.strongholdStatus = "Clearing waves"
                activateStrongholdPrompts()
                activateStrongholdWaves()
                nextTriggerAt = now + 4
            end

            if now >= fightDeadline then
                state.strongholdStatus = "Wave timeout - retrying"
                break
            end
            task.wait(0.35)
        end

        if not state.active or not state.diamondFarm then
            return
        end

        local chestDeadline = os.clock() + 20
        local chest = getStrongholdChest()
        while not chest and os.clock() < chestDeadline and state.diamondFarm do
            state.strongholdStatus = "Waiting for diamond chest"
            task.wait(0.25)
            chest = getStrongholdChest()
        end
        if not chest then
            state.strongholdStatus = "Diamond chest missing"
            return
        end

        state.strongholdStatus = "Opening diamond chest"
        openStrongholdDiamondChest(chest)

        local verifyDeadline = os.clock() + 18
        while state.active and state.diamondFarm and os.clock() < verifyDeadline do
            state.strongholdStatus = "Collecting diamonds"
            collectStrongholdDiamonds()

            local current = getDiamondCount()
            if current ~= nil and current > baseline then
                state.strongholdLastGain = current - baseline
                local totalGain = state.diamondScriptStart and (current - state.diamondScriptStart) or state.strongholdLastGain
                state.strongholdStatus = string.format("Verified +%d | session +%d", state.strongholdLastGain, math.max(0, totalGain))
                finishStrongholdControl(true)
                return
            end
            task.wait(0.35)
        end

        state.strongholdStatus = "No verified gain - retrying"
    end)

    if not ok then
        state.strongholdStatus = "Stronghold error - retrying"
    end
    if state.strongholdRunning then
        finishStrongholdControl(false)
    end
    return not state.strongholdControl
end

task.spawn(function()
    while state.active do
        local countdown = getStrongholdCountdownText()
        state.strongholdCountdown = countdown

        local doorOpen = strongholdDoorOpen()
        if state.strongholdCycleComplete and not doorOpen then
            local normalized = string.lower(string.gsub(countdown, "%s+", ""))
            if normalized ~= "00s" and normalized ~= "0s" and normalized ~= "ready" then
                state.strongholdCycleComplete = false
            end
        end

        if not state.diamondFarm then
            if state.strongholdControl or state.strongholdRunning then
                state.strongholdControl = false
                state.strongholdRunning = false
                state.strongholdStatus = "Off"
                if not state.autoFarm and state.strongholdManualKillRestore ~= nil then
                    state.killAura = state.strongholdManualKillRestore
                end
                state.strongholdManualKillRestore = nil
            else
                state.strongholdStatus = "Off"
            end
            task.wait(0.5)
        elseif state.strongholdControl and not state.strongholdRunning and os.clock() >= state.strongholdRetryAt then
            runStrongholdCycle()
            task.wait(0.25)
        elseif not state.strongholdCycleComplete and strongholdReady() and not state.strongholdRunning then
            runStrongholdCycle()
            task.wait(0.25)
        else
            if not state.strongholdRunning and not state.strongholdControl then
                state.strongholdStatus = "Waiting: " .. countdown
            end
            task.wait(0.35)
        end
    end
end)
'''
insert_before('\nlocal function getLostChildren()', stronghold_block, 'stronghold insertion')

# ---------------------------------------------------------------------------
# Existing systems must yield movement ownership to Stronghold.
# ---------------------------------------------------------------------------
replace_once(
    '''    if not state.autoFarm then
        return
    end

    local root = getRoot()''',
    '''    if not state.autoFarm or state.strongholdControl then
        return
    end

    local root = getRoot()''',
    'chest helper stronghold guard'
)

replace_once(
    '''        or state.resourceServiceRunning
        or isNight() then''',
    '''        or state.resourceServiceRunning
        or not state.autoCampBuild
        or state.strongholdControl
        or isNight() then''',
    'camp build stronghold guard'
)

replace_once(
    '''    if not state.active
        or not state.autoFarm
        or state.saplingServiceRunning
        or state.childRescueRunning then''',
    '''    if not state.active
        or not state.autoFarm
        or not state.autoPlant
        or state.saplingServiceRunning
        or state.childRescueRunning
        or state.strongholdControl then''',
    'sapling stronghold guard'
)

replace_once(
    '''        if state.autoFarm then
            openNearbyChests()
            task.wait(0.3)''',
    '''        if state.autoChest then
            openNearbyChests()
            task.wait(0.3)''',
    'auto chest state'
)

replace_once(
    '''        if campfireMaxed
            and state.autoFarm
            and not state.childRescueCompleted''',
    '''        if campfireMaxed
            and state.autoFarm
            and state.autoChildRescue
            and not state.strongholdControl
            and not state.childRescueCompleted''',
    'child rescue subfeature state'
)

replace_once(
    '''    if not state.autoFarm then
        return false
    end

    local root = getRoot()
    if not root or not root.Parent then''',
    '''    if not state.autoFarm or state.strongholdControl then
        return false
    end

    local root = getRoot()
    if not root or not root.Parent then''',
    'farm tween stronghold guard'
)

replace_once(
    '''        if not ignoreInterrupts
            and (state.emergencyFoodRun or foodServiceDue() or isNight() or state.childRescuePending or state.childRescueRunning) then''',
    '''        if not ignoreInterrupts
            and (state.strongholdControl or state.emergencyFoodRun or foodServiceDue() or isNight() or state.childRescuePending or state.childRescueRunning) then''',
    'farm tween interrupt stronghold'
)

# Auto Farm now owns and locks the entire suite, including Diamond Farm.
replace_once(
    '''    gear = false,
    smart = false,
    walkSpeed = 16,''',
    '''    gear = false,
    smart = false,
    plant = false,
    build = false,
    chest = false,
    child = false,
    diamond = false,
    walkSpeed = 16,''',
    'previous farm subfeatures'
)

replace_once(
    '''    previousFarm.gear = state.autoBestGear
    previousFarm.smart = state.smartResources''',
    '''    previousFarm.gear = state.autoBestGear
    previousFarm.smart = state.smartResources
    previousFarm.plant = state.autoPlant
    previousFarm.build = state.autoCampBuild
    previousFarm.chest = state.autoChest
    previousFarm.child = state.autoChildRescue
    previousFarm.diamond = state.diamondFarm''',
    'save farm subfeatures'
)

replace_once(
    '''    state.autoBestGear = true
    state.smartResources = true
    state.patrolIndex = 1''',
    '''    state.autoBestGear = true
    state.smartResources = true
    state.autoPlant = true
    state.autoCampBuild = true
    state.autoChest = true
    state.autoChildRescue = true
    state.diamondFarm = true
    state.patrolIndex = 1''',
    'force farm suite on'
)

replace_once(
    '''    state.autoBestGear = previousFarm.gear
    state.smartResources = previousFarm.smart''',
    '''    state.autoBestGear = previousFarm.gear
    state.smartResources = previousFarm.smart
    state.autoPlant = previousFarm.plant
    state.autoCampBuild = previousFarm.build
    state.autoChest = previousFarm.chest
    state.autoChildRescue = previousFarm.child
    state.diamondFarm = previousFarm.diamond''',
    'restore farm suite'
)

replace_once(
    '''    state.autoChop = true
    state.killAura = true
    state.autoBestGear = true
    state.smartResources = true

    if not farmPlatform or not farmPlatform.Parent then
        createPlatform()
    end

    lockFarmCharacter()''',
    '''    state.autoChop = true
    state.killAura = true
    state.autoBestGear = true
    state.smartResources = true
    state.autoPlant = true
    state.autoCampBuild = true
    state.autoChest = true
    state.autoChildRescue = true
    state.diamondFarm = true

    if not farmPlatform or not farmPlatform.Parent then
        createPlatform()
    end

    if state.strongholdControl then
        releaseFarmForStronghold()
    else
        lockFarmCharacter()
    end''',
    'heartbeat locked suite / movement ownership'
)

replace_once(
    '''        cancelFarmTween()
        createPlatform()
        pcall(character.PivotTo, character, CFrame.new(FARM_HOME))
        lockFarmCharacter()''',
    '''        cancelFarmTween()
        createPlatform()
        if state.strongholdControl then
            releaseFarmForStronghold()
        else
            pcall(character.PivotTo, character, CFrame.new(FARM_HOME))
            lockFarmCharacter()
        end''',
    'respawn stronghold ownership'
)

replace_once(
    '''        else
            local night = isNight()

            -- NIGHT: stay directly under center. No roaming.
            if night then''',
    '''        else
            -- Stronghold owns movement completely. This check happens before
            -- night detection, so night can never pull the player underground
            -- while waves/chest/diamond verification are in progress.
            if state.strongholdControl then
                releaseFarmForStronghold()
                wasNight = false
                task.wait(0.25)
                continue
            end

            local night = isNight()

            -- NIGHT: stay directly under center. No roaming.
            if night then''',
    'main farm stronghold priority'
)

# ---------------------------------------------------------------------------
# Replace the old flat UI with a collapsible responsive mobile UI.
# ---------------------------------------------------------------------------
ui_marker = '''--==============================================================
-- FINAL MINIMAL UI
--=============================================================='''
idx = s.find(ui_marker)
if idx < 0:
    raise RuntimeError('UI marker not found')
s = s[:idx] + r'''--==============================================================
-- RESPONSIVE COLLAPSIBLE UI
--==============================================================

local screen = Instance.new("ScreenGui")
screen.Name = "SB99_RedTeamUI"
screen.ResetOnSpawn = false
screen.DisplayOrder = 999999
screen.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
screen.IgnoreGuiInset = false
screen.Parent = playerGui

local frame = Instance.new("Frame")
frame.Name = "Main"
frame.Size = UDim2.fromOffset(310, 510)
frame.Position = UDim2.new(0.5, -155, 0.08, 0)
frame.BackgroundColor3 = Color3.fromRGB(18, 18, 22)
frame.BorderSizePixel = 0
frame.Active = true
frame.Parent = screen

local frameCorner = Instance.new("UICorner")
frameCorner.CornerRadius = UDim.new(0, 12)
frameCorner.Parent = frame

local stroke = Instance.new("UIStroke")
stroke.Color = Color3.fromRGB(75, 75, 88)
stroke.Thickness = 1
stroke.Parent = frame

local uiScale = Instance.new("UIScale")
uiScale.Parent = frame

local header = Instance.new("Frame")
header.Size = UDim2.new(1, 0, 0, 42)
header.BackgroundColor3 = Color3.fromRGB(29, 29, 35)
header.BorderSizePixel = 0
header.Active = true
header.Parent = frame

local headerCorner = Instance.new("UICorner")
headerCorner.CornerRadius = UDim.new(0, 12)
headerCorner.Parent = header

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, -52, 1, 0)
title.Position = UDim2.fromOffset(12, 0)
title.BackgroundTransparency = 1
title.Text = "Smile B • 99 Nights Helper"
title.TextColor3 = Color3.new(1, 1, 1)
title.TextXAlignment = Enum.TextXAlignment.Left
title.Font = Enum.Font.GothamBold
title.TextSize = 13
title.Parent = header

local minimize = Instance.new("TextButton")
minimize.Size = UDim2.fromOffset(30, 28)
minimize.Position = UDim2.new(1, -37, 0, 7)
minimize.BackgroundColor3 = Color3.fromRGB(48, 48, 57)
minimize.BorderSizePixel = 0
minimize.Text = "−"
minimize.TextColor3 = Color3.new(1, 1, 1)
minimize.Font = Enum.Font.GothamBold
minimize.TextSize = 18
minimize.Parent = header
local minimizeCorner = Instance.new("UICorner")
minimizeCorner.CornerRadius = UDim.new(0, 7)
minimizeCorner.Parent = minimize

local scroll = Instance.new("ScrollingFrame")
scroll.Name = "Sections"
scroll.Size = UDim2.new(1, -12, 1, -52)
scroll.Position = UDim2.fromOffset(6, 47)
scroll.BackgroundTransparency = 1
scroll.BorderSizePixel = 0
scroll.ScrollBarThickness = 4
scroll.ScrollBarImageColor3 = Color3.fromRGB(95, 95, 110)
scroll.CanvasSize = UDim2.new()
scroll.AutomaticCanvasSize = Enum.AutomaticSize.Y
scroll.ScrollingDirection = Enum.ScrollingDirection.Y
scroll.Parent = frame

local rootLayout = Instance.new("UIListLayout")
rootLayout.Padding = UDim.new(0, 6)
rootLayout.SortOrder = Enum.SortOrder.LayoutOrder
rootLayout.Parent = scroll

local rootPadding = Instance.new("UIPadding")
rootPadding.PaddingBottom = UDim.new(0, 8)
rootPadding.Parent = scroll

local refreshers = {}
local sections = {}

local function rounded(instance, radius)
    local corner = Instance.new("UICorner")
    corner.CornerRadius = UDim.new(0, radius or 8)
    corner.Parent = instance
end

local function makeSection(titleText, defaultOpen)
    local section = Instance.new("Frame")
    section.BackgroundColor3 = Color3.fromRGB(25, 25, 31)
    section.BorderSizePixel = 0
    section.Size = UDim2.new(1, -4, 0, 40)
    section.AutomaticSize = Enum.AutomaticSize.Y
    section.Parent = scroll
    rounded(section, 9)

    local layout = Instance.new("UIListLayout")
    layout.Padding = UDim.new(0, 4)
    layout.SortOrder = Enum.SortOrder.LayoutOrder
    layout.Parent = section

    local sectionPadding = Instance.new("UIPadding")
    sectionPadding.PaddingBottom = UDim.new(0, 5)
    sectionPadding.Parent = section

    local open = defaultOpen ~= false
    local button = Instance.new("TextButton")
    button.Size = UDim2.new(1, 0, 0, 36)
    button.BackgroundColor3 = Color3.fromRGB(35, 35, 43)
    button.BorderSizePixel = 0
    button.TextColor3 = Color3.fromRGB(225, 225, 235)
    button.Font = Enum.Font.GothamBold
    button.TextSize = 11
    button.TextXAlignment = Enum.TextXAlignment.Left
    button.LayoutOrder = 1
    button.Parent = section
    rounded(button, 8)

    local content = Instance.new("Frame")
    content.BackgroundTransparency = 1
    content.Size = UDim2.new(1, 0, 0, 0)
    content.AutomaticSize = Enum.AutomaticSize.Y
    content.LayoutOrder = 2
    content.Parent = section

    local contentLayout = Instance.new("UIListLayout")
    contentLayout.Padding = UDim.new(0, 4)
    contentLayout.SortOrder = Enum.SortOrder.LayoutOrder
    contentLayout.Parent = content

    local function refreshOpen()
        content.Visible = open
        button.Text = (open and "  ▼  " or "  ▶  ") .. titleText
    end
    refreshOpen()

    track(button.MouseButton1Click:Connect(function()
        open = not open
        refreshOpen()
    end))

    sections[titleText] = { frame = section, content = content, button = button }
    return content
end

local function makeStatus(parent, getter)
    local label = Instance.new("TextLabel")
    label.Size = UDim2.new(1, 0, 0, 30)
    label.BackgroundColor3 = Color3.fromRGB(31, 31, 38)
    label.BorderSizePixel = 0
    label.TextColor3 = Color3.fromRGB(205, 205, 215)
    label.Font = Enum.Font.Gotham
    label.TextSize = 10
    label.TextXAlignment = Enum.TextXAlignment.Left
    label.TextTruncate = Enum.TextTruncate.AtEnd
    label.Parent = parent
    rounded(label, 7)

    table.insert(refreshers, function()
        local ok, text = pcall(getter)
        label.Text = "   " .. (ok and tostring(text) or "Unavailable")
    end)
    return label
end

local function makeToggle(parent, labelText, getter, setter, farmLocked)
    local button = Instance.new("TextButton")
    button.Size = UDim2.new(1, 0, 0, 34)
    button.BorderSizePixel = 0
    button.TextColor3 = Color3.new(1, 1, 1)
    button.Font = Enum.Font.GothamBold
    button.TextSize = 10
    button.TextXAlignment = Enum.TextXAlignment.Left
    button.Parent = parent
    rounded(button, 7)

    local function refresh()
        local enabled = getter() == true
        local locked = farmLocked and state.autoFarm
        button.BackgroundColor3 = enabled and Color3.fromRGB(28, 112, 61) or Color3.fromRGB(47, 47, 56)
        if locked then
            button.Text = "   🔒 " .. labelText .. "   ON"
        else
            button.Text = "   " .. labelText .. (enabled and "   ON" or "   OFF")
        end
    end
    table.insert(refreshers, refresh)

    track(button.MouseButton1Click:Connect(function()
        if farmLocked and state.autoFarm then
            return
        end
        setter(not getter())
        for _, update in ipairs(refreshers) do
            pcall(update)
        end
    end))
    return button
end

local statusSection = makeSection("STATUS", true)
makeStatus(statusSection, function()
    local hunger = getRealHunger()
    return string.format("● Godmode Active   |   Hunger: %s", hunger and tostring(math.floor(hunger)) or "--")
end)
makeStatus(statusSection, function()
    local count = getDiamondCount()
    local start = state.diamondScriptStart
    local gained = count and start and math.max(0, count - start) or 0
    return string.format("Diamonds: %s   |   Script gain: +%d", count and tostring(count) or "--", gained)
end)
makeStatus(statusSection, function()
    return "Stronghold: " .. tostring(state.strongholdStatus) .. "   |   Timer: " .. tostring(state.strongholdCountdown)
end)

local farmSection = makeSection("AUTO FARM SUITE", true)
makeToggle(farmSection, "Auto Farm (locks full suite)", function() return state.autoFarm end, function(value)
    if value then enableFarm() else disableFarm() end
end, false)
makeToggle(farmSection, "Auto Chop", function() return state.autoChop end, function(v) state.autoChop = v end, true)
makeToggle(farmSection, "Kill Aura", function() return state.killAura end, function(v) state.killAura = v end, true)
makeToggle(farmSection, "Auto Best Gear", function() return state.autoBestGear end, function(v) state.autoBestGear = v end, true)
makeToggle(farmSection, "Smart Logs / Scrap", function() return state.smartResources end, function(v) state.smartResources = v end, true)
makeToggle(farmSection, "Open Nearby Chests", function() return state.autoChest end, function(v) state.autoChest = v end, true)
makeToggle(farmSection, "Plant Campfire Saplings", function() return state.autoPlant end, function(v) state.autoPlant = v end, true)
makeToggle(farmSection, "Upgrade Bench + Beds", function() return state.autoCampBuild end, function(v) state.autoCampBuild = v end, true)
makeToggle(farmSection, "Rescue All 4 Children", function() return state.autoChildRescue end, function(v) state.autoChildRescue = v end, true)

local strongholdSection = makeSection("STRONGHOLD / DIAMONDS", true)
makeToggle(strongholdSection, "Diamond Farm", function() return state.diamondFarm end, function(v)
    state.diamondFarm = v
    if not v then
        state.strongholdControl = false
        state.strongholdRunning = false
        state.strongholdStatus = "Off"
    end
end, true)
makeStatus(strongholdSection, function()
    if state.strongholdControl then
        return "Movement owner: Stronghold (night under-map disabled)"
    end
    return "Movement owner: Auto Farm / normal"
end)
makeStatus(strongholdSection, function()
    local baseline = state.strongholdBaseline
    return string.format("Run baseline: %s   |   Last verified: +%d", baseline and tostring(baseline) or "--", state.strongholdLastGain or 0)
end)

local infoSection = makeSection("INFO", false)
makeStatus(infoSection, function() return "Patrol: Y=60 • Night home: under center • Platform: Y=-54" end)
makeStatus(infoSection, function() return "Saplings: MainFire-centered rings every 10s within 100 studs" end)
makeStatus(infoSection, function() return "Credits: Smile B" end)

local ball = Instance.new("TextButton")
ball.Name = "SB_Ball"
ball.Size = UDim2.fromOffset(58, 58)
ball.Position = UDim2.new(0, 18, 0.5, -29)
ball.BackgroundColor3 = Color3.fromRGB(24, 24, 29)
ball.BorderSizePixel = 0
ball.Text = "SB"
ball.TextColor3 = Color3.new(1, 1, 1)
ball.Font = Enum.Font.GothamBold
ball.TextSize = 18
ball.Visible = false
ball.Active = true
ball.Parent = screen
rounded(ball, 29)
local ballStroke = Instance.new("UIStroke")
ballStroke.Thickness = 2
ballStroke.Color = Color3.fromRGB(105, 105, 120)
ballStroke.Parent = ball

local function clampToViewport(position, size)
    local camera = workspace.CurrentCamera
    local viewport = camera and camera.ViewportSize or Vector2.new(1280, 720)
    local maxX = math.max(0, viewport.X - size.X)
    local maxY = math.max(0, viewport.Y - size.Y)
    return Vector2.new(math.clamp(position.X, 0, maxX), math.clamp(position.Y, 0, maxY))
end

local lastViewport = Vector2.zero
local function refreshResponsiveLayout()
    local camera = workspace.CurrentCamera
    if not camera then return end
    local viewport = camera.ViewportSize
    if viewport == lastViewport then return end
    lastViewport = viewport

    -- Phone-first scaling. Width and height are both respected, with a lower
    -- bound that keeps touch rows usable instead of shrinking them to tiny text.
    local widthScale = (viewport.X - 12) / 310
    local heightScale = (viewport.Y - 12) / 510
    uiScale.Scale = math.clamp(math.min(1, widthScale, heightScale), 0.68, 1)

    task.defer(function()
        if not state.active then return end
        if frame.Visible then
            local position = clampToViewport(frame.AbsolutePosition, frame.AbsoluteSize)
            frame.Position = UDim2.fromOffset(position.X, position.Y)
        elseif ball.Visible then
            local position = clampToViewport(ball.AbsolutePosition, ball.AbsoluteSize)
            ball.Position = UDim2.fromOffset(position.X, position.Y)
        end
    end)
end

local function minimizeUI()
    local position = clampToViewport(frame.AbsolutePosition, ball.AbsoluteSize)
    ball.Position = UDim2.fromOffset(position.X, position.Y)
    frame.Visible = false
    ball.Visible = true
end

local function restoreUI()
    local position = clampToViewport(ball.AbsolutePosition, frame.AbsoluteSize)
    frame.Position = UDim2.fromOffset(position.X, position.Y)
    ball.Visible = false
    frame.Visible = true
end
track(minimize.MouseButton1Click:Connect(minimizeUI))

-- Main-window touch/mouse dragging with input ownership.
local dragging = false
local dragInput = nil
local dragTouch = nil
local dragStart = nil
local frameStart = nil
track(header.InputBegan:Connect(function(input)
    if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
        dragging = true
        dragStart = input.Position
        frameStart = frame.Position
        dragTouch = input.UserInputType == Enum.UserInputType.Touch and input or nil
        if dragTouch then dragInput = input end
    end
end))
track(header.InputChanged:Connect(function(input)
    if dragging and (input.UserInputType == Enum.UserInputType.MouseMovement or (dragTouch and input == dragTouch)) then
        dragInput = input
    end
end))
track(UserInputService.InputChanged:Connect(function(input)
    if dragging and input == dragInput and dragStart and frameStart then
        local delta = input.Position - dragStart
        local camera = workspace.CurrentCamera
        local viewport = camera and camera.ViewportSize or Vector2.zero
        local desired = Vector2.new(
            frameStart.X.Offset + delta.X + frameStart.X.Scale * viewport.X,
            frameStart.Y.Offset + delta.Y + frameStart.Y.Scale * viewport.Y
        )
        local clamped = clampToViewport(desired, frame.AbsoluteSize)
        frame.Position = UDim2.fromOffset(clamped.X, clamped.Y)
    end
end))
track(UserInputService.InputEnded:Connect(function(input)
    local endedOwner = dragging and ((dragTouch and input == dragTouch) or (not dragTouch and input.UserInputType == Enum.UserInputType.MouseButton1))
    if endedOwner then
        dragging = false
        dragInput = nil
        dragTouch = nil
        dragStart = nil
        frameStart = nil
    end
end))

-- Minimized SB ball: drag or tap to restore, including multi-touch ownership.
local ballDragging = false
local ballInput = nil
local ballTouch = nil
local ballStart = nil
local ballPositionStart = nil
local ballMoved = false
track(ball.InputBegan:Connect(function(input)
    if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
        ballDragging = true
        ballMoved = false
        ballStart = input.Position
        ballPositionStart = ball.Position
        ballTouch = input.UserInputType == Enum.UserInputType.Touch and input or nil
        if ballTouch then ballInput = input end
    end
end))
track(ball.InputChanged:Connect(function(input)
    if ballDragging and (input.UserInputType == Enum.UserInputType.MouseMovement or (ballTouch and input == ballTouch)) then
        ballInput = input
    end
end))
track(UserInputService.InputChanged:Connect(function(input)
    if not ballDragging or input ~= ballInput or not ballStart or not ballPositionStart then return end
    local delta = input.Position - ballStart
    if delta.Magnitude > 6 then ballMoved = true end
    local camera = workspace.CurrentCamera
    local viewport = camera and camera.ViewportSize or Vector2.zero
    local desired = Vector2.new(
        ballPositionStart.X.Offset + delta.X + ballPositionStart.X.Scale * viewport.X,
        ballPositionStart.Y.Offset + delta.Y + ballPositionStart.Y.Scale * viewport.Y
    )
    local clamped = clampToViewport(desired, ball.AbsoluteSize)
    ball.Position = UDim2.fromOffset(clamped.X, clamped.Y)
end))
track(UserInputService.InputEnded:Connect(function(input)
    local endedOwner = ballDragging and ((ballTouch and input == ballTouch) or (not ballTouch and input.UserInputType == Enum.UserInputType.MouseButton1))
    if not endedOwner then return end
    ballDragging = false
    ballInput = nil
    ballTouch = nil
    if not ballMoved and ball.Visible then restoreUI() end
end))

task.spawn(function()
    while state.active do
        for _, refresh in ipairs(refreshers) do
            pcall(refresh)
        end
        refreshResponsiveLayout()
        task.wait(0.4)
    end
end)

task.defer(function()
    refreshResponsiveLayout()
    for _, refresh in ipairs(refreshers) do pcall(refresh) end
end)
'''

# Static assertions for the intended behavior.
required = [
    'local RequestOpenItemChest = nil',
    'local RequestTakeDiamonds = nil',
    'diamondFarm = false',
    'strongholdControl = false',
    'state.diamondScriptStart = getDiamondCount()',
    'local function runStrongholdCycle()',
    'RequestOpenItemChest, 1.5, chest',
    'RequestTakeDiamonds, 0.75, object',
    'current > baseline',
    'if state.strongholdControl then\n                releaseFarmForStronghold()',
    'state.diamondFarm = true',
    'state.autoPlant = true',
    'state.autoCampBuild = true',
    'state.autoChest = true',
    'state.autoChildRescue = true',
    'RESPONSIVE COLLAPSIBLE UI',
    'AUTO FARM SUITE',
    'STRONGHOLD / DIAMONDS',
    'Diamond Farm',
    'Movement owner: Stronghold (night under-map disabled)',
]
for needle in required:
    if needle not in s:
        raise RuntimeError(f'missing required result: {needle!r}')

if 'FINAL MINIMAL UI' in s:
    raise RuntimeError('old flat UI still present')

TARGET.write_text(s, encoding='utf-8')
print('patched', len(s), 'bytes')
