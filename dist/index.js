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
  function MdWbShade (props) {
    return GenIcon({"tag":"svg","attr":{"viewBox":"0 0 24 24"},"child":[{"tag":"path","attr":{"fill":"none","d":"M0 0h24v24H0V0z"}},{"tag":"path","attr":{"d":"M14 12v2.5l5.5 5.5H22zm0 8h3l-3-3zM8 4l-6 6h2v10h8V10h2L8 4zm1 10H7v-4h2v4z"}}]})(props);
  }

  // ---- Display helpers ----
  /** Replace underscores with spaces and strip any trailing " [ShaderName]" bracket from labels */
  const formatDisplayName = (name) => name.replace(/\.fx$/i, "").replace(/_/g, " ").replace(/\s*\[.*?\]\s*$/, "").trim();
  // Global refresh function reference
  let forceRefreshContent = null;
  const Content = ({ serverAPI }) => {
      const baseShader = { data: "None", label: "No Shader" };
      const [shadersEnabled, setShadersEnabled] = React.useState(false);
      const [shader_list, set_shader_list] = React.useState([]);
      const [selectedShader, setSelectedShader] = React.useState(baseShader);
      const [shaderOptions, setShaderOptions] = React.useState([baseShader]);
      const [currentGameId, setCurrentGameId] = React.useState("Unknown");
      const [currentGameName, setCurrentGameName] = React.useState("Unknown");
      const [currentEffect, setCurrentEffect] = React.useState("");
      const [shaderParams, setShaderParams] = React.useState([]);
      const paramTimeouts = React.useRef({});
      const [applyDisabled, setApplyDisabled] = React.useState(false);
      // --- Add refreshVersion state for UI refreshes ---
      const [refreshVersion, setRefreshVersion] = React.useState(0);
      forceRefreshContent = () => setRefreshVersion(v => v + 1);
      const getShaderOptions = (le_list, baseShaderOrSS) => {
          let options = [];
          options.push(baseShaderOrSS);
          for (let i = 0; i < le_list.length; i++) {
              let option = { data: le_list[i], label: formatDisplayName(le_list[i]) };
              options.push(option);
          }
          return options;
      };
      const fetchShaderParams = async () => {
          const resp = await serverAPI.callPluginMethod("get_shader_params", {});
          if (resp.result && Array.isArray(resp.result)) {
              setShaderParams(resp.result);
          }
          else {
              setShaderParams([]);
          }
      };
      const refreshCurrentGameInfo = async () => {
          const appid = `${deckyFrontendLib.Router.MainRunningApp?.appid || "Unknown"}`;
          const appname = `${deckyFrontendLib.Router.MainRunningApp?.display_name || "Unknown"}`;
          setCurrentGameId(appid);
          setCurrentGameName(appname);
          await serverAPI.callPluginMethod("set_current_game_info", {
              appid,
              appname
          });
      };
      const initState = async () => {
          await refreshCurrentGameInfo();
          let shader_list = (await serverAPI.callPluginMethod("get_shader_list", {})).result;
          set_shader_list(shader_list);
          setShaderOptions(getShaderOptions(shader_list, baseShader));
          let enabledResp = await serverAPI.callPluginMethod("get_shader_enabled", {});
          let isEnabled = enabledResp.result === true || enabledResp.result === "true";
          setShadersEnabled(isEnabled);
          let curr = await serverAPI.callPluginMethod("get_current_shader", {});
          setSelectedShader({ data: curr.result, label: (curr.result == "0" ? "None" : formatDisplayName(curr.result)) });
          let eff = await serverAPI.callPluginMethod("get_current_effect", {});
          setCurrentEffect(eff.result.effect || "");
          // Fetch params for current shader
          await fetchShaderParams();
      };
      // --- Init state on mount and on refreshVersion bump ---
      React.useEffect(() => {
          initState();
      }, [refreshVersion]);
      // --- Helper to auto-apply the shader (forces gamescope reload) ---
      const applyShader = async () => {
          await serverAPI.callPluginMethod("apply_shader", {});
          let eff = await serverAPI.callPluginMethod("get_current_effect", {});
          setCurrentEffect(eff.result.effect || "");
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
          window.SP_REACT.createElement(deckyFrontendLib.PanelSection, { title: "Game" },
              window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, null,
                  window.SP_REACT.createElement("div", null,
                      window.SP_REACT.createElement("div", null,
                          window.SP_REACT.createElement("b", null, "Current Game:"),
                          " ",
                          currentGameName)))),
          window.SP_REACT.createElement(deckyFrontendLib.PanelSection, { title: "Shader" },
              window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, null,
                  window.SP_REACT.createElement(deckyFrontendLib.ToggleField, { label: "Enable Shaders", checked: shadersEnabled, onChange: async (enabled) => {
                          setShadersEnabled(enabled);
                          await serverAPI.callPluginMethod("set_shader_enabled", { isEnabled: enabled });
                          if (enabled) {
                              await serverAPI.callPluginMethod("toggle_shader", { shader_name: selectedShader.data });
                          }
                          else {
                              await serverAPI.callPluginMethod("toggle_shader", { shader_name: "None" });
                          }
                          let eff = await serverAPI.callPluginMethod("get_current_effect", {});
                          setCurrentEffect(eff.result.effect || "");
                      } })),
              window.SP_REACT.createElement(deckyFrontendLib.PanelSectionRow, null,
                  window.SP_REACT.createElement(deckyFrontendLib.Dropdown, { menuLabel: "Select shader", strDefaultLabel: selectedShader.label, rgOptions: shaderOptions, selectedOption: selectedShader, onChange: async (newSelectedShader) => {
                          setSelectedShader(newSelectedShader);
                          await serverAPI.callPluginMethod("set_shader", { "shader_name": newSelectedShader.data });
                          let eff = await serverAPI.callPluginMethod("get_current_effect", {});
                          setCurrentEffect(eff.result.effect || "");
                          // Fetch updated params for new shader
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
      //	let suspend_registers = [
      //		window.SteamClient.System.RegisterForOnSuspendRequest(logic.handleSuspend),
      //		window.SteamClient.System.RegisterForOnResumeFromSuspend(logic.handleResume),
      //	];
      let lastAppId = `${deckyFrontendLib.Router.MainRunningApp?.appid || "Unknown"}`;
      const interval = setInterval(async () => {
          const appid = `${deckyFrontendLib.Router.MainRunningApp?.appid || "Unknown"}`;
          const appname = `${deckyFrontendLib.Router.MainRunningApp?.display_name || "Unknown"}`;
          if (appid !== lastAppId) {
              lastAppId = appid;
              await serverApi.callPluginMethod("set_current_game_info", {
                  appid,
                  appname,
              });
              // --- Notify UI to refresh if overlay is open ---
              if (forceRefreshContent)
                  forceRefreshContent();
          }
      }, 5000);
      return {
          title: window.SP_REACT.createElement("div", { className: deckyFrontendLib.staticClasses.Title }, "Reshadeck"),
          content: window.SP_REACT.createElement(Content, { serverAPI: serverApi }),
          icon: window.SP_REACT.createElement(MdWbShade, null),
          onDismount() {
              //    suspend_registers[0].unregister();
              //    suspend_registers[1].unregister();
              clearInterval(interval);
          },
          alwaysRender: true
      };
  });

  return index;

})(DFL, SP_REACT);
