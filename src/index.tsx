import {
    ButtonItem,
    definePlugin,
    PanelSection,
    PanelSectionRow,
    ToggleField,
    Router,
    ServerAPI,
    staticClasses,
    Dropdown,
    DropdownItem,
    DropdownOption,
    SingleDropdownOption,
    SliderField,
    ConfirmModal,
    showModal
} from "decky-frontend-lib";
import { VFC, useState, useEffect, useRef, useMemo } from "react";
import { RiTvLine } from "react-icons/ri";

declare global {
    interface Window {
        SteamClient: any;
    }
}

// ---- Types ----
interface ShaderParam {
    name: string;
    type: string; // "float" | "bool" | "int"
    default: number | boolean;
    value: number | boolean;
    ui_type?: string;
    ui_min?: number;
    ui_max?: number;
    ui_step?: number;
    ui_label?: string;
    ui_items?: string[];
}

// ---- Display helpers ----
/** Replace underscores with spaces and strip any trailing " [ShaderName]" bracket from labels */
const formatDisplayName = (name: string): string =>
    name.replace(/\.fx$/i, "").replace(/_/g, " ").replace(/\s*\[.*?\]\s*$/, "").trim();

const baseShader = { data: "None", label: "No Shader" } as SingleDropdownOption;

const Content: VFC<{ serverAPI: ServerAPI }> = ({ serverAPI }) => {
    const [masterEnabled, setMasterEnabled] = useState<boolean>(true);
    const [shadersEnabled, setShadersEnabled] = useState<boolean>(false);
    const [selectedShader, setSelectedShader] = useState<DropdownOption>(baseShader);
    const [shaderList, setShaderList] = useState<string[]>([]);
    const [currentGameName, setCurrentGameName] = useState<string>("Unknown");

    // Packages
    const [packageOptions, setPackageOptions] = useState<DropdownOption[]>([]);
    const [selectedPackage, setSelectedPackage] = useState<DropdownOption>({ data: "Default", label: "Default" });

    const [shaderParams, setShaderParams] = useState<ShaderParam[]>([]);
    const paramTimeouts = useRef<{ [key: string]: number }>({});
    const [applyDisabled, setApplyDisabled] = useState(false);
    const [perGame, setPerGame] = useState<boolean>(false);

    const shaderDropdownOptions = useMemo((): DropdownOption[] => {
        const options: DropdownOption[] = [
            { label: "No Shader", data: -1 }
        ];
        shaderList.forEach((s, index) => {
            let label = formatDisplayName(s);
            // If inside a package/subfolder, show only the filename in the dropdown
            if (s.includes("/")) {
                const parts = s.split("/");
                label = formatDisplayName(parts[parts.length - 1]);
            }
            options.push({ label: label, data: index });
        });
        return options;
    }, [shaderList]);

    const fetchShaderParams = async () => {
        const resp = await serverAPI.callPluginMethod("get_shader_params", {});
        if (resp.result && Array.isArray(resp.result)) {
            setShaderParams(resp.result as ShaderParam[]);
        } else {
            setShaderParams([]);
        }
    };

    const initState = async () => {
        // 0. Get Master Switch
        const masterResp = await serverAPI.callPluginMethod("get_master_enabled", {});
        if (masterResp.success) {
            setMasterEnabled(masterResp.result as boolean);
        }

        // 1. Send active app info to backend
        const appid = `${Router.MainRunningApp?.appid || "Unknown"}`;
        const appname = `${Router.MainRunningApp?.display_name || "Unknown"}`;
        await serverAPI.callPluginMethod("set_current_game_info", { appid, appname });

        // 2. Refresh info from backend (gets resolved ID like 'steamos' and per-game status)
        const info = (await serverAPI.callPluginMethod("get_game_info", {})).result as any;
        setCurrentGameName(info.appname);
        setPerGame(info.per_game);

        // 3. Get packages
        // 3. Get packages
        const pkgResp = await serverAPI.callPluginMethod("get_shader_packages", {});
        const packages = (pkgResp.success && Array.isArray(pkgResp.result))
            ? (pkgResp.result as string[])
            : ["Default"];
        const pkgOptions = packages.map(p => ({ data: p, label: p } as SingleDropdownOption));
        setPackageOptions(pkgOptions);

        // 4. Get enabled status
        let enabledResp = await serverAPI.callPluginMethod("get_shader_enabled", {});
        let isEnabled: boolean = enabledResp.result === true || enabledResp.result === "true";
        setShadersEnabled(isEnabled);

        // 5. Get current shader
        let curr = await serverAPI.callPluginMethod("get_current_shader", {});
        let targetData = curr.result as string;
        if (targetData === "0") targetData = "None";

        // Determine package from current shader
        // Determine package logic:
        // 1. If shader path has '/', use folder name
        // 2. If shader != None, assume Default (or we'd need to search all)
        // 3. If shader == None, use persisted active_category from backend
        let initialPackage = info.active_category || "Default";

        if (targetData && targetData !== "None" && targetData.includes("/")) {
            initialPackage = targetData.split("/")[0];
        } else if (targetData && targetData !== "None") {
            initialPackage = "Default";
        }

        // Select package
        // Important: use find() on the NEW pkgOptions to get the exact object reference
        const matchedPkg = pkgOptions.find(p => p.data === initialPackage) || pkgOptions[0];
        setSelectedPackage(matchedPkg);

        // Get shader list for this package
        const fetchedShaderList = (await serverAPI.callPluginMethod("get_shader_list", { category: initialPackage })).result as string[];
        setShaderList(fetchedShaderList || []);

        if (targetData === "None") {
            setSelectedShader(baseShader);
        } else {
            // Simplified logic as we rely on indices for dropdown now
            const labelRaw = targetData.includes("/") ? targetData.split("/").pop()! : targetData;
            setSelectedShader({
                data: targetData,
                label: formatDisplayName(labelRaw)
            });
        }

        // 6. Fetch params
        await fetchShaderParams();
    }

    // --- Init state on mount ---
    useEffect(() => {
        initState();
    }, []);

    // --- Poll for game changes and re-init state ---
    useEffect(() => {
        let lastAppId = `${Router.MainRunningApp?.appid || "Unknown"}`;
        const interval = setInterval(async () => {
            const appid = `${Router.MainRunningApp?.appid || "Unknown"}`;
            if (appid !== lastAppId) {
                lastAppId = appid;
                await initState();
            }
        }, 5000);
        return () => clearInterval(interval);
    }, []);

    // --- Helper to auto-apply the shader (forces gamescope reload) ---
    const applyShader = async () => {
        await serverAPI.callPluginMethod("apply_shader", {});
    };

    // --- Helper to debounce parameter changes with auto-apply ---
    const handleParamChange = (paramName: string, value: number | boolean) => {
        // Update local state immediately for responsive UI
        setShaderParams(prev => prev.map(p =>
            p.name === paramName ? { ...p, value } : p
        ));
        // Debounce the backend call + auto-apply
        if (paramTimeouts.current[paramName]) {
            clearTimeout(paramTimeouts.current[paramName]);
        }
        paramTimeouts.current[paramName] = window.setTimeout(async () => {
            await serverAPI.callPluginMethod("set_shader_param", { name: paramName, value });
            await applyShader();
        }, 500);
    };

    // --- Render a single parameter control ---
    const renderParam = (p: ShaderParam) => {
        const isDisabled = !shadersEnabled || selectedShader.data === "None";

        if (p.type === "bool") {
            return (
                <PanelSectionRow key={p.name}>
                    <ToggleField
                        label={formatDisplayName(p.ui_label || p.name)}
                        checked={p.value as boolean}
                        disabled={isDisabled}
                        bottomSeparator="none"
                        onChange={(checked: boolean) => {
                            handleParamChange(p.name, checked);
                        }}
                    />
                </PanelSectionRow>
            );
        }

        // Combo / radio: render as dropdown with named options
        if (p.ui_items && p.ui_items.length > 0 && (p.ui_type === "combo" || p.ui_type === "radio")) {
            const comboOptions: DropdownOption[] = p.ui_items.map((label, idx) => ({
                data: idx,
                label: label,
            } as SingleDropdownOption));
            const currentIdx = typeof p.value === "number" ? p.value : 0;
            const selectedOption = comboOptions[currentIdx] || comboOptions[0];

            return (
                <PanelSectionRow key={p.name}>
                    <DropdownItem
                        label={formatDisplayName(p.ui_label || p.name)}
                        menuLabel={formatDisplayName(p.ui_label || p.name)}
                        rgOptions={comboOptions}
                        selectedOption={selectedOption.data}
                        disabled={isDisabled}
                        onChange={(opt: DropdownOption) => {
                            handleParamChange(p.name, opt.data as number);
                        }}
                    />
                </PanelSectionRow>
            );
        }

        if (p.type === "float" || p.type === "int") {
            const uiMin = p.ui_min ?? 0;
            const uiMax = p.ui_max ?? 2;
            const uiStep = p.ui_step ?? 0.01;

            // SliderField works with integer steps internally. We map the
            // float range [ui_min, ui_max] onto integer ticks.
            const numSteps = Math.round((uiMax - uiMin) / uiStep);
            const currentTick = Math.round(((p.value as number) - uiMin) / uiStep);

            return (
                <PanelSectionRow key={p.name}>
                    <SliderField
                        label={`${formatDisplayName(p.ui_label || p.name)}: ${(p.value as number).toFixed(2)}`}
                        min={0}
                        max={numSteps}
                        step={1}
                        value={currentTick}
                        disabled={isDisabled}
                        bottomSeparator="none"
                        onChange={(tick: number) => {
                            const real = uiMin + tick * uiStep;
                            // Clamp to avoid float drift
                            const clamped = Math.min(uiMax, Math.max(uiMin, parseFloat(real.toFixed(6))));
                            handleParamChange(p.name, clamped);
                        }}
                    />
                </PanelSectionRow>
            );
        }

        return null; // unsupported type (e.g. combo with single option)
    };

    const hasParams = shaderParams.length > 0;

    return (
        <div>
            <PanelSection>
                <PanelSectionRow>
                    <ToggleField
                        label="Master Switch"
                        checked={masterEnabled}
                        onChange={async (enabled: boolean) => {
                            setMasterEnabled(enabled);
                            await serverAPI.callPluginMethod("set_master_enabled", { enabled });
                        }}
                    />
                </PanelSectionRow>
                <PanelSectionRow>
                    <div style={{ fontSize: "0.85em", color: "#bbb", padding: "4px 0" }}>
                        Disable to prevent shaders from applying. Use this if a shader is causing crashes, so you can safely change the configuration.
                    </div>
                </PanelSectionRow>
            </PanelSection>

            <PanelSection>
                <PanelSectionRow>
                    <div style={{ display: "flex", flexDirection: "row" }}>
                        <span style={{ fontWeight: "bold", marginRight: "5px" }}>Profile:</span>
                        <span>{perGame ? currentGameName : "Default"}</span>
                    </div>
                </PanelSectionRow>
                <PanelSectionRow>
                    <ToggleField
                        label="Per-game profile"
                        checked={perGame}
                        onChange={async (checked: boolean) => {
                            setPerGame(checked);
                            await serverAPI.callPluginMethod("set_per_game", { enabled: checked });
                            // Reload info to sync with the switch between global/per-game
                            await initState();
                        }}
                    />
                </PanelSectionRow>
            </PanelSection>

            <PanelSection title="Shader">
                <PanelSectionRow>
                    <ToggleField
                        label="Enable"
                        checked={shadersEnabled}
                        bottomSeparator="none"
                        onChange={async (enabled: boolean) => {
                            setShadersEnabled(enabled);
                            await serverAPI.callPluginMethod("set_shader_enabled", { isEnabled: enabled });
                            await serverAPI.callPluginMethod("toggle_shader", {
                                shader_name: enabled ? selectedShader.data : "None"
                            });
                        }}
                    />
                </PanelSectionRow>
                <PanelSectionRow key="Package">
                    <DropdownItem
                        label="Package"
                        menuLabel="Package"
                        bottomSeparator="none"
                        rgOptions={packageOptions}
                        selectedOption={selectedPackage.data}
                        onChange={async (newPkg: DropdownOption) => {
                            if (newPkg.data === selectedPackage.data) {
                                return;
                            }
                            const matchedPkg = packageOptions.find(p => p.data === newPkg.data) || newPkg;
                            setSelectedPackage(matchedPkg);
                            await serverAPI.callPluginMethod("set_active_category", { category: newPkg.data });
                            try {
                                const resp = await serverAPI.callPluginMethod("get_shader_list", { category: newPkg.data });
                                const list = (resp.success && Array.isArray(resp.result))
                                    ? (resp.result as string[])
                                    : [];
                                setShaderList(list);
                            } catch (e) {
                                console.error("Failed to fetch shader list", e);
                                setShaderList([]);
                            }
                            setSelectedShader(baseShader);
                            await serverAPI.callPluginMethod("set_shader", { shader_name: "None" });
                            setShaderParams([]);
                        }}
                    />
                </PanelSectionRow>
                <PanelSectionRow key="Shader">
                    <DropdownItem
                        label="Shader"
                        menuLabel="Select shader"
                        rgOptions={shaderDropdownOptions}
                        selectedOption={
                            selectedShader.data === "None"
                                ? -1
                                : shaderList.indexOf(selectedShader.data as string)
                        }
                        onChange={async (opt: DropdownOption) => {
                            const idx = opt.data as number;
                            if (idx === -1) {
                                setSelectedShader(baseShader);
                                await serverAPI.callPluginMethod("set_shader", { shader_name: "None" });
                                setShaderParams([]);
                            } else {
                                const path = shaderList[idx];
                                const label = opt.label as string;
                                setSelectedShader({ data: path, label });
                                await serverAPI.callPluginMethod("set_shader", { shader_name: path });
                                await fetchShaderParams();
                            }
                        }}
                    />
                </PanelSectionRow>
            </PanelSection>

            {hasParams && (
                <PanelSection title="Parameters">
                    {shaderParams.map(p => renderParam(p))}
                    <PanelSectionRow>
                        <ButtonItem
                            disabled={!shadersEnabled || selectedShader.data === "None"}
                            bottomSeparator="none"
                            onClick={async () => {
                                await serverAPI.callPluginMethod("reset_shader_params", {});
                                await fetchShaderParams();
                                await applyShader();
                            }}
                        >Reset to Defaults</ButtonItem>
                    </PanelSectionRow>
                </PanelSection>
            )}



            <PanelSection title="Misc">
                <PanelSectionRow>
                    <ButtonItem
                        disabled={applyDisabled || !shadersEnabled || selectedShader.data === "None"}
                        bottomSeparator="none"
                        onClick={async () => {
                            setApplyDisabled(true);
                            setTimeout(() => setApplyDisabled(false), 1000);
                            await applyShader();
                        }}
                    >Force Apply</ButtonItem>
                </PanelSectionRow>

                <PanelSectionRow>
                    <ButtonItem
                        bottomSeparator="none"
                        onClick={() => {
                            showModal(
                                <ConfirmModal
                                    strTitle="Reset reshade directory?"
                                    strDescription="Are you sure? This will remove all files in ~/.local/share/gamescope/reshade and replace them with the default files from this plugin."
                                    onOK={async () => {
                                        await serverAPI.callPluginMethod("reset_reshade_directory", {});
                                        await initState();
                                    }}
                                />
                            );
                        }}
                    >
                        Reset Local Reshade Directory
                    </ButtonItem>
                </PanelSectionRow>

                <PanelSectionRow>
                    <ButtonItem
                        bottomSeparator="none"
                        onClick={() => {
                            showModal(
                                <ConfirmModal
                                    strTitle="Reset configuration?"
                                    strDescription="Are you sure? This will reset all plugin settings, including per-game profiles and shader parameters."
                                    onOK={async () => {
                                        await serverAPI.callPluginMethod("reset_configuration", {});
                                        await initState();
                                    }}
                                />
                            );
                        }}
                    >
                        Reset configuration
                    </ButtonItem>
                </PanelSectionRow>

                <PanelSectionRow>
                    <ButtonItem
                        bottomSeparator="none"
                        onClick={async () => {
                            await serverAPI.callPluginMethod("cleanup_legacy_files", {});
                            await initState(); // Refresh list potentially
                        }}
                    >
                        Clean legacy temp files
                    </ButtonItem>
                </PanelSectionRow>

            </PanelSection>

            <PanelSection title="Information">
                <PanelSectionRow>
                    <div>Place any custom shaders in <pre>~/.local/share/gamescope</pre><pre>/reshade/Shaders</pre> so that the .fx files are in the root of the Shaders folder.</div>
                </PanelSectionRow>
                <PanelSectionRow>
                    <div>WARNING: Shaders can lead to dropped frames and possibly even severe performance problems.</div>
                </PanelSectionRow>
            </PanelSection>
        </div>
    );
};

export default definePlugin((serverApi: ServerAPI) => {
    let unregisterMonitor: (() => void) | undefined;

    const checkGame = async () => {
        try {
            const appid = `${Router.MainRunningApp?.appid || "Unknown"}`;
            const appname = `${Router.MainRunningApp?.display_name || "Unknown"}`;
            await serverApi.callPluginMethod("set_current_game_info", { appid, appname });
        } catch (e) {
            console.error("Reshadeck checkGame error", e);
        }
    };

    // Use SteamClient events to detect game launch/close in the background
    if (window.SteamClient?.GameSessions?.RegisterForAppLifetimeNotifications) {
        const sub = window.SteamClient.GameSessions.RegisterForAppLifetimeNotifications((update: any) => {
            // Detect game launch -> trigger shader application immediately
            if (update.bCreated) {
                const appid = update.unAppID.toString();
                let appname = "Loading...";
                // Best effort to get name if Router is already updated
                if (Router.MainRunningApp && String(Router.MainRunningApp.appid) === appid) {
                    appname = Router.MainRunningApp.display_name;
                }
                serverApi.callPluginMethod("set_current_game_info", { appid, appname });
            }

            // Wait slightly for Router to update its state (for game close or accurate name)
            // 250ms: fast check for quick transitions
            // 500ms: standard check
            // 1500ms: backup check
            setTimeout(checkGame, 250);
            setTimeout(checkGame, 500);
            setTimeout(checkGame, 1500);
        });
        unregisterMonitor = () => {
            if (sub?.unregister) sub.unregister();
        };
    } else {
        // Fallback polling if SteamClient/Events are missing
        const i = setInterval(checkGame, 2000);
        unregisterMonitor = () => clearInterval(i);
    }

    // Initial check
    checkGame();

    return {
        title: <div className={staticClasses.Title}>Reshadeck+</div>,
        content: <Content serverAPI={serverApi} />,
        icon: <RiTvLine />,
        onDismount() {
            if (unregisterMonitor) unregisterMonitor();
        },
    };
});
