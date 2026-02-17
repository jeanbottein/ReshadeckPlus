(function (deckyFrontendLib, React) {
  'use strict';

  function _interopDefaultLegacy (e) { return e && typeof e === 'object' && 'default' in e ? e : { 'default': e }; }

  var React__default = /*#__PURE__*/_interopDefaultLegacy(React);

  var DefaultContext = {
    color: undefined,
    size: undefined,
    className: undefined,
    style: undefined,
    attr: undefined
  };
  var IconContext = React__default["default"].createContext && React__default["default"].createContext(DefaultContext);

  var __assign = window && window.__assign || function () {
    __assign = Object.assign || function (t) {
      for (var s, i = 1, n = arguments.length; i < n; i++) {
        s = arguments[i];
        for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p)) t[p] = s[p];
      }
      return t;
    };
    return __assign.apply(this, arguments);
  };
  var __rest = window && window.__rest || function (s, e) {
    var t = {};
    for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p) && e.indexOf(p) < 0) t[p] = s[p];
    if (s != null && typeof Object.getOwnPropertySymbols === "function") for (var i = 0, p = Object.getOwnPropertySymbols(s); i < p.length; i++) {
      if (e.indexOf(p[i]) < 0 && Object.prototype.propertyIsEnumerable.call(s, p[i])) t[p[i]] = s[p[i]];
    }
    return t;
  };
  function Tree2Element(tree) {
    return tree && tree.map(function (node, i) {
      return React__default["default"].createElement(node.tag, __assign({
        key: i
      }, node.attr), Tree2Element(node.child));
    });
  }
  function GenIcon(data) {
    // eslint-disable-next-line react/display-name
    return function (props) {
      return React__default["default"].createElement(IconBase, __assign({
        attr: __assign({}, data.attr)
      }, props), Tree2Element(data.child));
    };
  }
  function IconBase(props) {
    var elem = function (conf) {
      var attr = props.attr,
        size = props.size,
        title = props.title,
        svgProps = __rest(props, ["attr", "size", "title"]);
      var computedSize = size || conf.size || "1em";
      var className;
      if (conf.className) className = conf.className;
      if (props.className) className = (className ? className + " " : "") + props.className;
      return React__default["default"].createElement("svg", __assign({
        stroke: "currentColor",
        fill: "currentColor",
        strokeWidth: "0"
      }, conf.attr, attr, svgProps, {
        className: className,
        style: __assign(__assign({
          color: props.color || conf.color
        }, conf.style), props.style),
        height: computedSize,
        width: computedSize,
        xmlns: "http://www.w3.org/2000/svg"
      }), title && React__default["default"].createElement("title", null, title), props.children);
    };
    return IconContext !== undefined ? React__default["default"].createElement(IconContext.Consumer, null, function (conf) {
      return elem(conf);
    }) : elem(DefaultContext);
  }

  // THIS FILE IS AUTO GENERATED
  function RiTvLine (props) {
    return GenIcon({"tag":"svg","attr":{"viewBox":"0 0 24 24"},"child":[{"tag":"path","attr":{"d":"M15.4142 5.00004H21.0082C21.556 5.00004 22 5.44467 22 6.00091V19.9992C22 20.5519 21.5447 21 21.0082 21H2.9918C2.44405 21 2 20.5554 2 19.9992V6.00091C2 5.44815 2.45531 5.00004 2.9918 5.00004H8.58579L6.05025 2.46451L7.46447 1.05029L11.4142 5.00004H12.5858L16.5355 1.05029L17.9497 2.46451L15.4142 5.00004ZM4 7.00004V19H20V7.00004H4Z"}}]})(props);
  }

  // ---- Display helpers ----
  /** Replace underscores with spaces and strip any trailing " [ShaderName]" bracket from labels */
  const formatDisplayName = (name) => name.replace(/\.fx$/i, "").replace(/_/g, " ").replace(/\s*\[.*?\]\s*$/, "").trim();
  const Content = ({ serverAPI }) => {
      const baseShader = { data: "None", label: "No Shader" };
      const [shadersEnabled, setShadersEnabled] = React.useState(false);
      const [selectedShader, setSelectedShader] = React.useState(baseShader);
      const [shaderOptions, setShaderOptions] = React.useState([baseShader]);
      const [currentGameName, setCurrentGameName] = React.useState("Unknown");
      const [shaderParams, setShaderParams] = React.useState([]);
      const paramTimeouts = React.useRef({});
      const [applyDisabled, setApplyDisabled] = React.useState(false);
      const [perGame, setPerGame] = React.useState(false);
      const [currentAppId, setCurrentAppId] = React.useState("Unknown");
      const getShaderOptions = (shaderList) => [
          baseShader,
          ...shaderList.map(s => ({ data: s, label: formatDisplayName(s) }))
      ];
      const fetchShaderParams = async () => {
          const resp = await serverAPI.callPluginMethod("get_shader_params", {});
          if (resp.result && Array.isArray(resp.result)) {
              setShaderParams(resp.result);
          }
          else {
              setShaderParams([]);
          }
      };
      const initState = async () => {
          // 1. Send active app info to backend
          const appid = `${deckyFrontendLib.Router.MainRunningApp?.appid || "Unknown"}`;
          const appname = `${deckyFrontendLib.Router.MainRunningApp?.display_name || "Unknown"}`;
          await serverAPI.callPluginMethod("set_current_game_info", { appid, appname });
          // 2. Refresh info from backend (gets resolved ID like 'steamos' and per-game status)
          const info = (await serverAPI.callPluginMethod("get_game_info", {})).result;
          setCurrentAppId(info.appid);
          setCurrentGameName(info.appname);
          setPerGame(info.per_game);
          // 3. Get shader list
          const shaderList = (await serverAPI.callPluginMethod("get_shader_list", {})).result;
          setShaderOptions(getShaderOptions(shaderList));
          // 4. Get enabled status
          let enabledResp = await serverAPI.callPluginMethod("get_shader_enabled", {});
          let isEnabled = enabledResp.result === true || enabledResp.result === "true";
          setShadersEnabled(isEnabled);
          // 5. Get current shader
          let curr = await serverAPI.callPluginMethod("get_current_shader", {});
          setSelectedShader({
              data: curr.result,
              label: (curr.result == "None" || curr.result == "0" ? "None" : formatDisplayName(curr.result))
          });
          // 6. Fetch params
          await fetchShaderParams();
      };
      // --- Init state on mount ---
      React.useEffect(() => {
          initState();
      }, []);
      // --- Poll for game changes and re-init state ---
      React.useEffect(() => {
          let lastAppId = `${deckyFrontendLib.Router.MainRunningApp?.appid || "Unknown"}`;
          const interval = setInterval(async () => {
              const appid = `${deckyFrontendLib.Router.MainRunningApp?.appid || "Unknown"}`;
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
      const handleParamChange = (paramName, value) => {
          // Update local state immediately for responsive UI
          setShaderParams(prev => prev.map(p => p.name === paramName ? { ...p, value } : p));
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
      const renderParam = (p) => {
          const isDisabled = !shadersEnabled || selectedShader.data === "None";
          if (p.type === "bool") {
              return (window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, { key: p.name },
                  window.SP_REACT.createElement(deckyFrontendLib.ToggleField, { label: formatDisplayName(p.ui_label || p.name), checked: p.value, disabled: isDisabled, onChange: (checked) => {
                          handleParamChange(p.name, checked);
                      } })));
          }
          // Combo / radio: render as dropdown with named options
          if (p.ui_items && p.ui_items.length > 0 && (p.ui_type === "combo" || p.ui_type === "radio")) {
              const comboOptions = p.ui_items.map((label, idx) => ({
                  data: idx,
                  label: label,
              }));
              const currentIdx = typeof p.value === "number" ? p.value : 0;
              return (window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, { key: p.name },
                  window.SP_REACT.createElement("div", { style: { marginBottom: "4px", fontSize: "12px" } }, formatDisplayName(p.ui_label || p.name)),
                  window.SP_REACT.createElement(deckyFrontendLib.Dropdown, { menuLabel: formatDisplayName(p.ui_label || p.name), strDefaultLabel: p.ui_items[currentIdx] || "Unknown", rgOptions: comboOptions, selectedOption: currentIdx, disabled: isDisabled, onChange: (opt) => {
                          handleParamChange(p.name, opt.data);
                      } })));
          }
          if (p.type === "float" || p.type === "int") {
              const uiMin = p.ui_min ?? 0;
              const uiMax = p.ui_max ?? 2;
              const uiStep = p.ui_step ?? 0.01;
              // SliderField works with integer steps internally. We map the
              // float range [ui_min, ui_max] onto integer ticks.
              const numSteps = Math.round((uiMax - uiMin) / uiStep);
              const currentTick = Math.round((p.value - uiMin) / uiStep);
              return (window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, { key: p.name },
                  window.SP_REACT.createElement(deckyFrontendLib.SliderField, { bottomSeparator: "none", label: `${formatDisplayName(p.ui_label || p.name)}: ${p.value.toFixed(2)}`, min: 0, max: numSteps, step: 1, value: currentTick, disabled: isDisabled, onChange: (tick) => {
                          const real = uiMin + tick * uiStep;
                          // Clamp to avoid float drift
                          const clamped = Math.min(uiMax, Math.max(uiMin, parseFloat(real.toFixed(6))));
                          handleParamChange(p.name, clamped);
                      } })));
          }
          return null; // unsupported type (e.g. combo with single option)
      };
      const hasParams = shaderParams.length > 0;
      return (window.SP_REACT.createElement("div", null,
          window.SP_REACT.createElement(deckyFrontendLib.PanelSection, { title: "Notice" },
              window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, null,
                  window.SP_REACT.createElement("div", { style: { fontSize: "12px" } }, "Shader application is not automatic in the background. You must reopen the plugin to apply the settings profile."))),
          window.SP_REACT.createElement(deckyFrontendLib.PanelSection, { title: "Game" },
              window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, null,
                  window.SP_REACT.createElement(deckyFrontendLib.ToggleField, { label: "Per-Game Profile", checked: perGame, onChange: async (checked) => {
                          setPerGame(checked);
                          await serverAPI.callPluginMethod("set_per_game", { enabled: checked });
                          // Reload info to sync with the switch between global/per-game
                          await initState();
                      } })),
              perGame && (window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, null,
                  window.SP_REACT.createElement("div", { style: { display: "flex", flexDirection: "column", alignItems: "center", width: "100%", gap: "8px" } },
                      currentAppId !== "steamos" && currentAppId !== "Unknown" && (window.SP_REACT.createElement("img", { src: `https://cdn.cloudflare.steamstatic.com/steam/apps/${currentAppId}/header.jpg`, alt: currentGameName, style: { width: "95%", borderRadius: "4px" }, onError: (e) => { e.currentTarget.style.display = 'none'; } })),
                      window.SP_REACT.createElement("div", { style: { fontWeight: "bold" } }, currentGameName))))),
          window.SP_REACT.createElement(deckyFrontendLib.PanelSection, { title: "Shader" },
              window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, null,
                  window.SP_REACT.createElement(deckyFrontendLib.ToggleField, { label: "Enable Shaders", checked: shadersEnabled, onChange: async (enabled) => {
                          setShadersEnabled(enabled);
                          await serverAPI.callPluginMethod("set_shader_enabled", { isEnabled: enabled });
                          await serverAPI.callPluginMethod("toggle_shader", {
                              shader_name: enabled ? selectedShader.data : "None"
                          });
                      } })),
              window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, null,
                  window.SP_REACT.createElement(deckyFrontendLib.Dropdown, { menuLabel: "Select shader", strDefaultLabel: selectedShader.label, rgOptions: shaderOptions, selectedOption: selectedShader, onChange: async (newSelectedShader) => {
                          setSelectedShader(newSelectedShader);
                          await serverAPI.callPluginMethod("set_shader", { shader_name: newSelectedShader.data });
                          await fetchShaderParams();
                      } }))),
          hasParams && (window.SP_REACT.createElement(deckyFrontendLib.PanelSection, { title: "Parameters" },
              shaderParams.map(p => renderParam(p)),
              window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, null,
                  window.SP_REACT.createElement(deckyFrontendLib.ButtonItem, { disabled: !shadersEnabled || selectedShader.data === "None", onClick: async () => {
                          await serverAPI.callPluginMethod("reset_shader_params", {});
                          await fetchShaderParams();
                          await applyShader();
                      } }, "Reset to Defaults")))),
          window.SP_REACT.createElement(deckyFrontendLib.PanelSection, { title: "Misc" },
              window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, null,
                  window.SP_REACT.createElement(deckyFrontendLib.ButtonItem, { disabled: applyDisabled || !shadersEnabled || selectedShader.data === "None", onClick: async () => {
                          setApplyDisabled(true);
                          setTimeout(() => setApplyDisabled(false), 1000);
                          await applyShader();
                      } }, "Force Apply"))),
          window.SP_REACT.createElement(deckyFrontendLib.PanelSection, { title: "Information" },
              window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, null,
                  window.SP_REACT.createElement("div", null,
                      "Place any custom shaders in ",
                      window.SP_REACT.createElement("pre", null, "~/.local/share/gamescope"),
                      window.SP_REACT.createElement("pre", null, "/reshade/Shaders"),
                      " so that the .fx files are in the root of the Shaders folder.")),
              window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, null,
                  window.SP_REACT.createElement("div", null, "WARNING: Shaders can lead to dropped frames and possibly even severe performance problems.")))));
  };
  var index = deckyFrontendLib.definePlugin((serverApi) => {
      let unregisterMonitor;
      const checkGame = async () => {
          try {
              const appid = `${deckyFrontendLib.Router.MainRunningApp?.appid || "Unknown"}`;
              const appname = `${deckyFrontendLib.Router.MainRunningApp?.display_name || "Unknown"}`;
              await serverApi.callPluginMethod("set_current_game_info", { appid, appname });
          }
          catch (e) {
              console.error("Reshadeck checkGame error", e);
          }
      };
      // Use SteamClient events to detect game launch/close in the background
      if (window.SteamClient?.GameSessions?.RegisterForAppLifetimeNotifications) {
          const sub = window.SteamClient.GameSessions.RegisterForAppLifetimeNotifications((update) => {
              // Detect game launch -> trigger shader application immediately
              if (update.bCreated) {
                  const appid = update.unAppID.toString();
                  let appname = "Loading...";
                  // Best effort to get name if Router is already updated
                  if (deckyFrontendLib.Router.MainRunningApp && String(deckyFrontendLib.Router.MainRunningApp.appid) === appid) {
                      appname = deckyFrontendLib.Router.MainRunningApp.display_name;
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
              if (sub?.unregister)
                  sub.unregister();
          };
      }
      else {
          // Fallback polling if SteamClient/Events are missing
          const i = setInterval(checkGame, 2000);
          unregisterMonitor = () => clearInterval(i);
      }
      // Initial check
      checkGame();
      return {
          title: window.SP_REACT.createElement("div", { className: deckyFrontendLib.staticClasses.Title }, "Reshadeck+"),
          content: window.SP_REACT.createElement(Content, { serverAPI: serverApi }),
          icon: window.SP_REACT.createElement(RiTvLine, null),
          onDismount() {
              if (unregisterMonitor)
                  unregisterMonitor();
          },
      };
  });

  return index;

})(DFL, SP_REACT);
