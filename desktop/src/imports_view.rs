use super::{tool_name, Catalog, MUTED};
use eframe::egui::{self, RichText};
use std::{
    collections::BTreeSet,
    fs,
    path::Path,
    time::{Duration, Instant},
};

const SOURCES: [&str; 6] = [
    "codex",
    "claude",
    "claude-desktop",
    "workbuddy",
    "openclaw",
    "dsh",
];

#[derive(Debug, PartialEq)]
pub(super) enum Action {
    Run(Vec<String>),
    ImportChatgpt,
}

pub(super) struct Panel {
    pub open: bool,
    pub storage: bool,
    sources: BTreeSet<String>,
    text_only: bool,
    kinds: BTreeSet<String>,
    snapshots: bool,
    pub started: Option<Instant>,
    pub cleanup_plan: Option<serde_json::Value>,
    pub message: Option<String>,
    cleanup_confirmed: bool,
}

impl Panel {
    pub fn load(root: &Path) -> Self {
        let saved: serde_json::Value = fs::read_to_string(root.join(".import-policy.json"))
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or_default();
        let sources = saved["tools"]
            .as_array()
            .map(|a| {
                a.iter()
                    .filter_map(|v| v.as_str())
                    .filter(|s| SOURCES.contains(s))
                    .map(String::from)
                    .collect()
            })
            .unwrap_or_else(|| SOURCES.map(String::from).into_iter().collect());
        Self {
            open: false,
            storage: false,
            sources,
            text_only: saved["text_only"].as_bool().unwrap_or(true),
            kinds: fs::read_to_string(root.join(".migration.json"))
                .ok()
                .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
                .and_then(|v| v["kinds"].as_array().cloned())
                .map(|a| {
                    a.iter()
                        .filter_map(|v| v.as_str())
                        .filter(|s| super::attachments_view::KINDS.iter().any(|(k, _)| k == s))
                        .map(String::from)
                        .collect()
                })
                .unwrap_or_else(|| ["images".into()].into_iter().collect()),
            snapshots: saved["source_snapshots"]
                .as_bool()
                .unwrap_or(saved["text_only"] == false),
            started: None,
            cleanup_plan: None,
            message: None,
            cleanup_confirmed: false,
        }
    }

    pub fn show(
        &mut self,
        ctx: &egui::Context,
        root: &Path,
        catalog: &Catalog,
        busy: bool,
        status: &str,
    ) -> Option<Action> {
        let mut action = None;
        let mut open = self.open;
        let screen = ctx.screen_rect();
        egui::Window::new(if self.storage { "存储空间" } else { "收集本机聊天记录" })
            .id(egui::Id::new("collect-or-storage"))
            .open(&mut open).default_width(540.0).resizable(false).movable(false)
            .default_height(if self.storage { 260.0 } else { (screen.height() - 160.0).clamp(300.0, 620.0) })
            .fixed_pos(egui::pos2(((screen.width() - 560.0) * 0.5).max(12.0), 72.0))
            .vscroll(true).max_height((screen.height() - 100.0).max(200.0)).show(ctx, |ui| {
                if self.storage {
                    self.storage_content(ui, busy, &mut action);
                } else {
                    ui.label(RichText::new("选择这台电脑上用过的 AI 应用").size(18.0).strong());
                    ui.label(RichText::new("只读取本地已有记录，保存到当前星匣档案。不会修改原应用文件。").small().color(MUTED));
                    ui.add_space(12.0);
                    ui.add_enabled_ui(!busy, |ui| {
                        ui.horizontal(|ui| {
                            if ui.small_button("全选").clicked() { self.sources = SOURCES.map(String::from).into_iter().collect(); }
                            if ui.small_button("清空").clicked() { self.sources.clear(); }
                        });
                        egui::Grid::new("import-source-options").num_columns(2).spacing(egui::vec2(16.0, 6.0)).show(ui, |ui| {
                            for (index, source) in SOURCES.into_iter().enumerate() {
                                let count = catalog.sessions.iter().filter(|s| s.meta.tool == source && !super::claude_projects_view::is_timeline_item(s)).count();
                                let mut selected = self.sources.contains(source);
                                if ui.checkbox(&mut selected, format!("{}    已收集 {count} 条", tool_name(source))).changed() {
                                    if selected { self.sources.insert(source.into()); } else { self.sources.remove(source); }
                                }
                                if index % 2 == 1 { ui.end_row(); }
                            }
                        });
                        ui.label(RichText::new("Claude App 包含本地普通聊天、Code 导入副本和 Projects；缓存可能不完整。").small().color(MUTED));
                        ui.add_space(12.0);
                        ui.separator();
                        ui.label(RichText::new("保存哪些内容").strong());
                        ui.horizontal(|ui| {
                            ui.radio_value(&mut self.text_only, true, "仅文字（推荐）");
                            ui.radio_value(&mut self.text_only, false, "自选附件");
                        });
                        ui.label(RichText::new(if self.text_only {
                            "保存用户与助手原文、来源和项目关系。已有图片等副本继续保留，可在“存储空间”中单独清理。"
                        } else { "文字始终保存；只复制勾选的附件，不递归复制项目目录。" }).small().color(MUTED));
                        ui.add_enabled_ui(!self.text_only, |ui| {
                            egui::Grid::new("import-content-options").num_columns(3).spacing(egui::vec2(20.0, 5.0)).show(ui, |ui| {
                                for (index, (kind, label)) in super::attachments_view::KINDS.iter().enumerate() {
                                    let mut selected = self.kinds.contains(*kind);
                                    if ui.checkbox(&mut selected, *label).changed() {
                                        if selected { self.kinds.insert((*kind).into()); } else { self.kinds.remove(*kind); }
                                    }
                                    if index % 3 == 2 { ui.end_row(); }
                                }
                            });
                            if self.kinds.contains("logs") { self.snapshots = true; }
                            ui.add_enabled(!self.kinds.contains("logs"), egui::Checkbox::new(&mut self.snapshots, "另存完整事件快照（占用较多空间）"));
                            if self.kinds.contains("logs") {
                                ui.label(RichText::new("提取命令与日志需要完整事件快照，已一并勾选。").small().color(MUTED));
                            }
                        });
                        ui.add_space(12.0);
                        let button = ui.push_id("import-selected-action", |ui| ui.add_enabled(!self.sources.is_empty(), egui::Button::new(RichText::new("开始收集所选来源").color(egui::Color32::WHITE)).fill(super::ACCENT))).inner;
                        if button.clicked() {
                            let mut args = vec!["import-local".into(), "--tools".into(), self.sources.iter().cloned().collect::<Vec<_>>().join(",")];
                            if !self.text_only {
                                args.extend(["--resource-kinds".into(), if self.kinds.is_empty() { "none".into() } else { self.kinds.iter().cloned().collect::<Vec<_>>().join(",") }]);
                                if self.snapshots { args.push("--source-snapshots".into()); }
                            }
                            self.cleanup_plan = None;
                            action = Some(Action::Run(args));
                        }
                        ui.label(RichText::new("重复收集只更新有变化的会话。只有点击按钮才开始收集。").small().color(MUTED));
                        ui.add_space(16.0);
                        ui.separator();
                        egui::CollapsingHeader::new("从导出文件补充（可选）").show(ui, |ui| {
                            ui.label(RichText::new("手上已有 ChatGPT 导出的 JSON / ZIP 时，可补充到当前档案。这个入口不扫描本机应用，也不登录账号。").small().color(MUTED));
                            if ui.button("选择 ChatGPT 导出文件…").clicked() { action = Some(Action::ImportChatgpt); }
                        });
                    });
                }
                ui.add_space(12.0);
                ui.add(egui::Label::new(RichText::new(format!("保存到：{}", root.display())).small().color(MUTED)).truncate()).on_hover_text(root.display().to_string());
                if busy {
                    ui.spinner();
                    if let Some(started) = self.started {
                        ui.label(RichText::new(format!("已运行 {} 秒 · 可以继续浏览聊天", started.elapsed().as_secs())).small().color(MUTED));
                        ctx.request_repaint_after(Duration::from_secs(1));
                    }
                }
                ui.label(RichText::new(self.message.as_deref().unwrap_or(status)).small().color(MUTED));
            });
        self.open = open;
        if let Some(Action::Run(args)) = &mut action {
            args.extend(["--archive".into(), root.to_string_lossy().to_string()]);
        }
        action
    }

    fn storage_content(&mut self, ui: &mut egui::Ui, busy: bool, action: &mut Option<Action>) {
        ui.label(RichText::new("释放星匣副本占用").size(18.0).strong());
        ui.label(RichText::new("保留聊天文字和 Projects 关系，只清理星匣复制的图片、附件与完整事件快照。原应用文件保持不变；仅存在于这些副本中的资源清理后无法从这里恢复。").small().color(MUTED));
        ui.add_space(12.0);
        ui.add_enabled_ui(!busy, |ui| {
            if ui.button("估算可释放空间").clicked() {
                self.cleanup_confirmed = false;
                *action = Some(Action::Run(vec!["cleanup-text".into(), "--plan".into()]));
            }
            if let Some(plan) = &self.cleanup_plan {
                ui.label(format!(
                    "可释放约 {:.2} GB · {} 个副本 · 保留 {} 个会话的文字",
                    plan["estimated_bytes"].as_u64().unwrap_or(0) as f64 / 1e9,
                    plan["files"],
                    plan["sessions"]
                ));
                ui.checkbox(
                    &mut self.cleanup_confirmed,
                    "确认清理资源副本，之后仅保存文字",
                );
                if ui
                    .add_enabled(
                        self.cleanup_confirmed && plan["files"].as_u64().unwrap_or(0) > 0,
                        egui::Button::new("清理副本并保留文字"),
                    )
                    .clicked()
                {
                    *action = Some(Action::Run(vec!["cleanup-text".into()]));
                }
            }
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn labels(output: &egui::FullOutput) -> Vec<(String, egui::Pos2)> {
        fn visit(shape: &egui::Shape, result: &mut Vec<(String, egui::Pos2)>) {
            match shape {
                egui::Shape::Text(text) => result.push((
                    text.galley.text().into(),
                    shape.visual_bounding_rect().center(),
                )),
                egui::Shape::Vec(items) => {
                    for item in items {
                        visit(item, result);
                    }
                }
                _ => {}
            }
        }
        let mut result = Vec::new();
        for shape in &output.shapes {
            visit(&shape.shape, &mut result);
        }
        result
    }

    #[test]
    fn source_selection_waits_for_explicit_import_and_uses_text_mode() {
        check_import_options(true, false, &[]);
        check_import_options(false, false, &["--resource-kinds", "documents,images"]);
        check_import_options(
            false,
            true,
            &["--resource-kinds", "documents,images", "--source-snapshots"],
        );
    }

    fn check_import_options(text_only: bool, snapshots: bool, extra: &[&str]) {
        let ctx = egui::Context::default();
        crate::setup(&ctx, 15.0);
        ctx.style_mut(|style| style.animation_time = 0.0);
        let root = Path::new("/synthetic/starvault/archive");
        let mut panel = Panel::load(root);
        panel.open = true;
        panel.text_only = text_only;
        panel.snapshots = snapshots;
        panel.kinds = ["images".into(), "documents".into()].into_iter().collect();
        panel.sources = ["codex".into(), "claude".into()].into_iter().collect();
        let mut source = egui::Pos2::ZERO;
        let mut import = egui::Pos2::ZERO;
        for frame in 0..20 {
            let position = if frame < 14 { source } else { import };
            let events = if [10, 11, 16, 17].contains(&frame) {
                vec![
                    egui::Event::PointerMoved(position),
                    egui::Event::PointerButton {
                        pos: position,
                        button: egui::PointerButton::Primary,
                        pressed: frame == 10 || frame == 16,
                        modifiers: egui::Modifiers::NONE,
                    },
                ]
            } else {
                vec![]
            };
            let mut action = None;
            let output = ctx.run(
                egui::RawInput {
                    screen_rect: Some(egui::Rect::from_min_size(
                        egui::Pos2::ZERO,
                        egui::vec2(1000.0, 1000.0),
                    )),
                    time: Some(frame as f64 / 10.0),
                    events,
                    ..Default::default()
                },
                |ctx| {
                    action = panel.show(ctx, root, &Catalog::default(), false, "");
                },
            );
            let text = labels(&output);
            if let Some((_, pos)) = text.iter().find(|(t, _)| t.starts_with("Claude Code")) {
                source = *pos;
            }
            if let Some((_, pos)) = text.iter().find(|(t, _)| t == "开始收集所选来源") {
                import = *pos;
            }
            if frame == 1 {
                assert!(
                    source != egui::Pos2::ZERO && import != egui::Pos2::ZERO,
                    "{text:?}"
                );
            }
            if frame == 11 {
                assert_eq!(
                    panel.sources,
                    ["codex".into()].into_iter().collect(),
                    "source click at {source:?}"
                );
            }
            if frame == 17 {
                assert_eq!(
                    action
                        .unwrap_or_else(|| panic!("import click at {import:?}, labels: {text:?}")),
                    Action::Run(
                        [
                            vec!["import-local", "--tools", "codex"],
                            extra.to_vec(),
                            vec!["--archive", "/synthetic/starvault/archive"]
                        ]
                        .concat()
                        .into_iter()
                        .map(String::from)
                        .collect()
                    )
                );
            } else {
                assert!(
                    action.is_none(),
                    "checking a source must not start an import"
                );
            }
        }
    }
}
