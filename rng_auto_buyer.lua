-- Smile B RNG loader / safe state hotfix
-- Uses the last full UI/database build as the core, then patches only the runtime
-- state machine. This keeps saved settings/UI/database features while removing
-- the movement/camera/spin retry behavior that could cause resets or missed counts.

local BASE_URL = "https://raw.githubusercontent.com/Smile-B14/Roblox/f502f70903337c0ea95e8ae08220becdb3769072/rng_auto_buyer.lua"

local ok, source = pcall(function()
    return game:HttpGet(BASE_URL)
end)
if not ok or type(source) ~= "string" then
    warn("[SmileB RNG] Failed to download core:", source)
    return
end

local function replaceTopFunction(name, replacement)
    local marker = "local function " .. name .. "("
    local s = source:find(marker, 1, true)
    if not s then
        warn("[SmileB RNG] Patch function not found:", name)
        return false
    end
    local nextFn = source:find("\nlocal function ", s + #marker, true)
    if not nextFn then
        warn("[SmileB RNG] Could not find end boundary for:", name)
        return false
    end
    source = source:sub(1, s - 1) .. replacement .. source:sub(nextFn + 1)
    return true
end

local function replaceSection(startMarker, endMarker, replacement)
    local s = source:find(startMarker, 1, true)
    if not s then
        warn("[SmileB RNG] Patch section start not found:", startMarker)
        return false
    end
    local e = source:find(endMarker, s + #startMarker, true)
    if not e then
        warn("[SmileB RNG] Patch section end not found:", endMarker)
        return false
    end
    source = source:sub(1, s - 1) .. replacement .. source:sub(e)
    return true
end

-- Never move/rotate the character root to face a prompt.
assert(replaceSection("local function FaceTarget(pos)", "local cameraAimToken = 0", [[local function FaceTarget(pos)
    return
end

]]))

-- Never manipulate CurrentCamera. Camera movement is not needed for fireproximityprompt.
assert(replaceSection("local function AimCameraFor(target, duration)", "local PromptBusy=", [[local function AimCameraFor(target, duration)
    return
end

]]))

-- Simple machine movement. Keep the player's CURRENT Y so MoveTo never tries to
-- walk the Humanoid into a floor because the saved machine coordinates use Y=-6.
assert(replaceTopFunction("MoveDirect", [[local function MoveDirect(pos, timeout)
    if not State.Running or State.Dead or not Root or not Root.Parent or not Humanoid or Humanoid.Health <= 0 then return false end
    local target = Vector3.new(pos.X, Root.Position.Y, pos.Z)
    if FlatDistance(Root.Position, target) <= ARRIVAL_DISTANCE then return true end
    Humanoid:MoveTo(target)
    local started = os.clock()
    local last = Root.Position
    local lastMoved = os.clock()
    while State.Running and not State.Dead and Humanoid.Health > 0 and Root.Parent do
        if FlatDistance(Root.Position, target) <= ARRIVAL_DISTANCE then return true end
        if (Root.Position - last).Magnitude > 0.45 then
            last = Root.Position
            lastMoved = os.clock()
        elseif os.clock() - lastMoved > 1.15 then
            Humanoid.Jump = true
            lastMoved = os.clock()
        end
        if os.clock() - started > (timeout or 5) then return false end
        task.wait(.06)
    end
    return false
end
]]))

-- Safe adaptive movement. For the nearby spinner/buy positions use only normal
-- Humanoid:MoveTo. Pathfinding/jump recovery is reserved for Honey.
assert(replaceTopFunction("MoveAdaptive", [[local function MoveAdaptive(pos, maxAttempts)
    if not State.Running or State.Dead or not Root or not Root.Parent or not Humanoid or Humanoid.Health <= 0 then return false end

    local isMachineTarget = FlatDistance(pos, SPIN_POSITION) < 2 or FlatDistance(pos, BUY_POSITION) < 2
    if isMachineTarget then
        return MoveDirect(pos, 5)
    end

    maxAttempts = maxAttempts or 4
    for attempt = 1, maxAttempts do
        if not State.Running or State.Dead or Humanoid.Health <= 0 then return false end
        local waypoints = ComputePath(pos)
        if not waypoints then return false end

        local failed = false
        for _, wp in ipairs(waypoints) do
            if not State.Running or State.Dead or Humanoid.Health <= 0 then return false end
            if wp.Action == Enum.PathWaypointAction.Jump then Humanoid.Jump = true end
            Humanoid:MoveTo(wp.Position)
            local started = os.clock()
            local last = Root.Position
            local lastMoved = os.clock()
            while State.Running and not State.Dead and Humanoid.Health > 0 and FlatDistance(Root.Position, wp.Position) > ARRIVAL_DISTANCE do
                if (Root.Position - last).Magnitude > .55 then
                    last = Root.Position
                    lastMoved = os.clock()
                elseif os.clock() - lastMoved > .95 then
                    failed = true
                    break
                end
                if os.clock() - started > 3 then failed = true break end
                task.wait(.05)
            end
            if failed then break end
        end
        if not failed and FlatDistance(Root.Position, pos) <= 6 then return true end

        local side = (attempt % 2 == 0) and -1 or 1
        Humanoid.Jump = true
        Humanoid:MoveTo(Root.Position + Vector3.new(3 * side, 0, 0))
        task.wait(.35)
    end
    return false
end
]]))

assert(replaceTopFunction("PrepareSpinner", [[local function PrepareSpinner()
    State.Phase = "RETURN_START"
    return MoveDirect(SPIN_POSITION, 5)
end
]]))

-- Honey is completely idle when workspace.Honey does not exist.
assert(replaceTopFunction("CollectHoneyIfPresent", [[local function CollectHoneyIfPresent()
    local honey = workspace:FindFirstChild("Honey")
    if not honey or not honey.Parent then return false end
    State.Phase = "HONEY"
    local started = os.clock()

    while State.Running and not State.Dead and Humanoid and Humanoid.Health > 0 and honey.Parent and os.clock() - started < HONEY_SAFETY_TIMEOUT do
        local hp = InstancePosition(honey)
        if not hp then return false end
        if not MoveAdaptive(hp, 4) then return false end
        if not honey.Parent or workspace:FindFirstChild("Honey") ~= honey then return true end

        local prompt = honey:FindFirstChildWhichIsA("ProximityPrompt", true)
        if prompt and prompt.Enabled and not PromptBusy[prompt] then FirePromptOnce(prompt) end
        if FlatDistance(Root.Position, hp) <= 5 then
            Humanoid.Jump = true
            Humanoid:MoveTo(hp)
            task.wait(.3)
        end
        if not honey.Parent or workspace:FindFirstChild("Honey") ~= honey then return true end
        task.wait(.12)
    end
    return not honey.Parent
end
]]))

-- Count only a NEW result whose buy prompt is actually ready.
assert(replaceSection("-- Detect the next result, but DO NOT move toward it and DO NOT evaluate/buy yet.", "-- Once we decide to buy, no code path can call the spin prompt until this returns.", [[-- Safe confirmed-result spin detector.
local function GetReadyResult()
    local folder = workspace:FindFirstChild("RNGMachineDisplay")
    if not folder then return nil, nil end
    local bestModel, bestPrompt, bestDistance = nil, nil, math.huge
    for _, model in ipairs(folder:GetChildren()) do
        if model:IsA("Model") then
            local root = model:FindFirstChild("RootPart")
            local prompt = GetBuyPrompt(model)
            if root and prompt and prompt.Parent and prompt.Enabled then
                local d = (root.Position - BUY_POSITION).Magnitude
                if d < ACTIVE_RANGE and d < bestDistance then
                    bestModel, bestPrompt, bestDistance = model, prompt, d
                end
            end
        end
    end
    return bestModel, bestPrompt
end

local function SpinAndDetectNewResult()
    if not PrepareSpinner() then return nil end
    State.Phase = "SPINNING"

    local oldModel, oldPrompt = GetReadyResult()
    local transitioned = oldModel == nil

    local temp = {}
    if oldPrompt then
        temp[#temp + 1] = oldPrompt.AncestryChanged:Connect(function(_, parent)
            if not parent then transitioned = true end
        end)
        temp[#temp + 1] = oldPrompt:GetPropertyChangedSignal("Enabled"):Connect(function()
            if not oldPrompt.Enabled then transitioned = true end
        end)
    end
    if oldModel and oldModel:FindFirstChild("RootPart") then
        temp[#temp + 1] = oldModel.RootPart.ChildRemoved:Connect(function(child)
            if child.Name == "PromptAttachment" then transitioned = true end
        end)
    end

    if not FirePromptOnce(SpinPrompt) then
        for _, c in ipairs(temp) do pcall(function() c:Disconnect() end) end
        return nil
    end

    local started = os.clock()
    local result = nil
    while State.Running and not State.Dead and Humanoid and Humanoid.Health > 0 and os.clock() - started < SPIN_TRANSITION_TIMEOUT do
        if oldModel then
            local currentOldPrompt = GetBuyPrompt(oldModel)
            if not IsResultVisible(oldModel) or not currentOldPrompt or currentOldPrompt ~= oldPrompt then transitioned = true end
        end

        local model, prompt = GetReadyResult()
        if model and prompt then
            if oldModel == nil then
                result = model
                break
            elseif model ~= oldModel then
                result = model
                break
            elseif transitioned then
                result = model
                break
            end
        end
        task.wait(.04)
    end

    for _, c in ipairs(temp) do pcall(function() c:Disconnect() end) end
    if result then task.wait(.10) end
    return result
end

local function WaitUntilResultReady(model)
    if not model then return nil end
    local started = os.clock()
    while State.Running and not State.Dead and Humanoid and Humanoid.Health > 0 and os.clock() - started < RESULT_READY_TIMEOUT do
        local prompt = GetBuyPrompt(model)
        if prompt and prompt.Parent and prompt.Enabled then return prompt end
        task.wait(.04)
    end
    return nil
end

]]))

-- Hard buy lock, with no camera behavior and no fast prompt spam.
assert(replaceSection("local function BuyLocked(model)", "local Spins=0", [[local function BuyLocked(model)
    State.Phase = "BUY_LOCK"
    local firstPrompt = GetBuyPrompt(model)
    if not firstPrompt or not firstPrompt.Enabled then return false end
    if not MoveDirect(BUY_POSITION, 5) then return false end

    local started = os.clock()
    local attempts = 0
    while State.Running and not State.Dead and Humanoid and Humanoid.Health > 0 and os.clock() - started < BUY_SAFETY_TIMEOUT do
        local prompt = GetBuyPrompt(model)
        if not IsResultVisible(model) and not prompt then return true end

        if prompt and prompt.Enabled and not PromptBusy[prompt] then
            if FirePromptOnce(prompt) then
                attempts += 1
                local hold = tonumber(prompt.HoldDuration) or 0
                local waitUntil = os.clock() + math.max(hold, .05) + .35
                while State.Running and not State.Dead and Humanoid.Health > 0 and os.clock() < waitUntil do
                    if not IsResultVisible(model) and not GetBuyPrompt(model) then return true end
                    task.wait(.04)
                end
            end
        else
            task.wait(.08)
        end
    end
    SetStatus("Buy lock ended after " .. attempts .. " tries")
    return not IsResultVisible(model)
end
]]))

-- One spin per cycle; no immediate spam when a result is missed.
assert(replaceSection("local Spins=0", "Track(StartButton.MouseButton1Click", [[local Spins = 0

local function HandleHoneyOnly()
    local honey = workspace:FindFirstChild("Honey")
    if not honey or not honey.Parent then return false end
    SetStatus("Honey found | collecting...")
    return CollectHoneyIfPresent()
end

local function MainLoop()
    if State.LoopRunning then return end
    State.LoopRunning = true

    while State.Running and not State.Dead and not GameData.Ready do
        SetStatus("Waiting for live database...")
        task.wait(.1)
    end
    if not State.Running or State.Dead or not Humanoid or Humanoid.Health <= 0 then
        State.LoopRunning = false
        return
    end

    if workspace:FindFirstChild("Honey") then HandleHoneyOnly() end

    while State.Running and not State.Dead and Humanoid and Humanoid.Health > 0 do
        SetStatus("Returning to start...")
        if not PrepareSpinner() then
            SetStatus("Can't reach spinner | retrying safely")
            task.wait(.6)
            continue
        end

        SetStatus("Spinning once...")
        local current = SpinAndDetectNewResult()
        if not current then
            SetStatus("Result not confirmed | waiting before retry")
            task.wait(1.5)
            continue
        end

        local readyPrompt = WaitUntilResultReady(current)
        if not readyPrompt then
            SetStatus("Result readiness lost | waiting before retry")
            task.wait(1.5)
            continue
        end

        Spins += 1
        local mutation = DetectMutation(current)
        local buy, data, nameMatch, moneyMatch, actual = ShouldBuy(current, mutation)
        local rarity = data and data.Rarity or "?"
        ResultLabel.Text = "Spins: " .. Spins .. "\n" .. current.Name .. " | " .. mutation .. " | " .. rarity .. " | $" .. FormatMoney(actual) .. "/s" .. (mutation ~= "Normal" and (" | " .. string.format("%.3gx", GetMutationMultiplier(mutation))) or "")
        print("[SmileB RNG] CONFIRMED SPIN", Spins, current.Name, "income", actual, "nameMatch", nameMatch, "moneyMatch", moneyMatch)

        if buy then
            local reason = (nameMatch and moneyMatch) and "Name + Money" or (nameMatch and "Name" or "Money")
            SetStatus("FOUND " .. reason .. " | buying...")
            SendWebhook(current.Name, data, mutation, actual, reason)
            BuyLocked(current)
        else
            SetStatus("Not targeted")
        end

        if workspace:FindFirstChild("Honey") then HandleHoneyOnly() end

        if State.Running and Humanoid and Humanoid.Health > 0 then
            SetStatus("Returning to start...")
            PrepareSpinner()
        end
    end

    State.LoopRunning = false
    if not State.Dead then SetStatus("Stopped") end
end

]]))

-- Stop on death instead of automatically continuing on a fresh spawn.
local respawnMarker = [[Track(Player.CharacterAdded:Connect(function()task.wait(.7);if not State.Dead then LoadCharacter()end end))]]
local respawnReplacement = [[Track(Humanoid.Died:Connect(function()
    State.Running = false
    State.LoopRunning = false
    State.Phase = "DIED"
    pcall(function() SetStatus("Character died | automation stopped") end)
end))
Track(Player.CharacterAdded:Connect(function()
    task.wait(.7)
    if not State.Dead then
        LoadCharacter()
        pcall(function() SetStatus("Respawned | press START to continue") end)
    end
end))]]
local rs, re = source:find(respawnMarker, 1, true)
if rs then
    source = source:sub(1, rs - 1) .. respawnReplacement .. source:sub(re + 1)
else
    warn("[SmileB RNG] Respawn safety marker not found")
end

local oldVersion = 'local VERSION = "2026-08-09-ready-lock-v1"'
local newVersion = 'local VERSION = "2026-08-09-safe-state-v3"'
local vs, ve = source:find(oldVersion, 1, true)
if vs then source = source:sub(1, vs - 1) .. newVersion .. source:sub(ve + 1) end

local fn, compileErr = loadstring(source)
if not fn then
    warn("[SmileB RNG] Patched core compile failed:", compileErr)
    return
end

local success, runtimeErr = pcall(fn)
if not success then
    warn("[SmileB RNG] Patched core runtime failed:", runtimeErr)
    return
end

print("[SmileB RNG] Safe-state hotfix active")
print("[SmileB RNG] No camera writes, no root CFrame writes, no rapid missed-spin retry spam")