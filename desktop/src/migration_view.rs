//! The main workflow is collect, take the archive, then open it on another computer.
use super::{brand, claude_projects_view, Catalog, ACCENT, INK, LINE, MUTED};
use eframe::egui::{self, RichText};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeSet, path::Path};

#[derive(Clone, Copy, Default, Deserialize, Serialize, PartialEq)]
pub(super) enum Workspace {
    Transfer,
    #[default]
    Library,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(super) enum Action {
    Collect,
    Check,
    Export,
    Open,
    Library,
    Reveal,
    RevealExport,
    Storage,
    Resources,
    Skills,
}

#[derive(Default)]
pub(super) struct State {
    pub report: Option<serde_json::Value>,
    pub message: String,
}

pub(super) fn navigation(ui: &mut egui::Ui, workspace: &mut Workspace) -> bool {
    let before = *workspace;
    for (page, title) in [
        (Workspace::Library, "聊天档案"),
        (Workspace::Transfer, "备份与迁移"),
    ] {
        ui.selectable_value(workspace, page, title);
    }
    *workspace != before
}

fn step(
    ui: &mut egui::Ui,
    number: &str,
    title: &str,
    detail: &str,
    button: &str,
    enabled: bool,
    primary: bool,
) -> bool {
    egui::Frame::new()
        .fill(egui::Color32::WHITE)
        .stroke(egui::Stroke::new(1.0, LINE))
        .corner_radius(14)
        .inner_margin(18)
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.set_min_height(188.0);
            ui.label(RichText::new(number).small().strong().color(ACCENT));
            ui.add_space(5.0);
            ui.label(RichText::new(title).size(19.0).strong().color(INK));
            ui.add_space(8.0);
            ui.allocate_ui_with_layout(
                egui::vec2(ui.available_width(), 62.0),
                egui::Layout::top_down(egui::Align::Min),
                |ui| {
                    ui.label(RichText::new(detail).size(13.0).color(MUTED));
                },
            );
            ui.add_space(8.0);
            let mut widget = egui::Button::new(RichText::new(button).color(if primary {
                egui::Color32::WHITE
            } else {
                INK
            }));
            if primary {
                widget = widget.fill(ACCENT).stroke(egui::Stroke::NONE);
            }
            ui.add_enabled(
                enabled,
                widget.min_size(egui::vec2(ui.available_width(), 35.0)),
            )
            .clicked()
        })
        .inner
}

fn size(bytes: u64) -> String {
    if bytes >= 1_000_000_000 {
        format!("{:.2} GB", bytes as f64 / 1e9)
    } else if bytes >= 1_000_000 {
        format!("{:.1} MB", bytes as f64 / 1e6)
    } else {
        format!("{:.0} KB", bytes as f64 / 1e3)
    }
}

impl State {
    pub fn show(
        &self,
        ui: &mut egui::Ui,
        root: &Path,
        catalog: &Catalog,
        busy: bool,
        loading: bool,
    ) -> Option<Action> {
        let mut action = None;
        egui::ScrollArea::vertical().id_salt("migration-home").auto_shrink([false, false]).show(ui, |ui| {
            let width = ui.available_width().min(1060.0);
            let margin = ((ui.available_width() - width) * 0.5).max(0.0);
            ui.horizontal_top(|ui| {
                let spacing = ui.spacing().item_spacing.x;
                ui.spacing_mut().item_spacing.x = 0.0;
                ui.add_space(margin);
                ui.vertical(|ui| {
                    ui.spacing_mut().item_spacing.x = spacing;
                    ui.set_width(width);
                    ui.add_space(24.0);
                    ui.label(RichText::new("换电脑，聊天记录也一起带走。").size(29.0).strong());
                    ui.add_space(6.0);
                    ui.label(RichText::new("从这台电脑收集，在新电脑继续查找和阅读。").size(14.0).color(MUTED));
                    ui.add_space(24.0);
                    ui.columns(3, |columns| {
                        if step(&mut columns[0], "01 · 旧电脑", "收集本机记录", "选择用过的 AI 应用，把本地聊天保存进星匣。默认只保存文字，重复收集只更新变化。", "选择来源并收集", !busy, true) {
                            action = Some(Action::Collect);
                        }
                        if step(&mut columns[1], "02 · 带走", "导出档案文件夹", "检查现有档案，再另存到移动硬盘或自选位置。已有的图片、附件和 Skill 副本也一起带走。", if self.report.is_some() { "选择位置并导出" } else { "检查档案并准备导出" }, !busy && !catalog.sessions.is_empty(), false) {
                            action = Some(if self.report.is_some() { Action::Export } else { Action::Check });
                        }
                        if step(&mut columns[2], "03 · 新电脑", "打开已有档案", "选择从旧电脑带来的星匣档案文件夹，即可搜索、阅读和查看项目时间线。", "选择档案文件夹", !busy, false) {
                            action = Some(Action::Open);
                        }
                    });
                    ui.add_space(22.0);
                    egui::Frame::new().fill(egui::Color32::WHITE).stroke(egui::Stroke::new(1.0, LINE)).corner_radius(12).inner_margin(20).show(ui, |ui| {
                        ui.set_width(ui.available_width());
                        ui.horizontal(|ui| {
                            brand::mark(ui, 27.0);
                            ui.label(RichText::new("当前档案").size(17.0).strong());
                            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                if ui.add_enabled(!loading && !catalog.sessions.is_empty(), egui::Button::new("浏览聊天档案 →").frame(false)).clicked() { action = Some(Action::Library); }
                            });
                        });
                        let count = catalog.sessions.iter().filter(|s| !claude_projects_view::is_timeline_item(s)).count();
                        let sources: BTreeSet<_> = catalog.sessions.iter().map(|s| &s.meta.tool).collect();
                        let devices: BTreeSet<_> = catalog.sessions.iter().map(|s| &s.device).collect();
                        ui.add_space(10.0);
                        ui.label(RichText::new(if loading { "正在读取档案…".into() } else if count == 0 { "还没有聊天记录。从第 1 步收集，或在第 3 步打开已有档案。".into() } else { format!("{count} 段对话  ·  {} 种来源  ·  {} 台电脑", sources.len(), devices.len()) }).color(MUTED));
                        ui.horizontal(|ui| {
                            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                if ui.small_button("查看位置").clicked() { action = Some(Action::Reveal); }
                                ui.add(egui::Label::new(RichText::new(root.display().to_string()).small().color(MUTED)).truncate()).on_hover_text(root.display().to_string());
                            });
                        });
                    });
                    if let Some(report) = &self.report {
                        ui.add_space(14.0);
                        egui::Frame::new().fill(super::SELECTED).corner_radius(10).inner_margin(16).show(ui, |ui| {
                            ui.set_width(ui.available_width());
                            ui.label(RichText::new(if report["plan"] == false { "档案已导出，可以带走了" } else { "档案检查通过，可以选择保存位置" }).strong().color(ACCENT));
                            ui.label(format!("{} 段对话 · {} 个文件 · 约 {} · {} 个图片 / 附件副本 · {} 个 Skill", report["sessions"], report["files"], size(report["bytes"].as_u64().unwrap_or(0)), report["resources"], report["skills"]));
                            if let Some(destination) = report["destination"].as_str() {
                                ui.add(egui::Label::new(destination).truncate()).on_hover_text(destination);
                                if ui.button("打开导出位置").clicked() { action = Some(Action::RevealExport); }
                            } else {
                                ui.label(RichText::new("导出范围是当前档案中的全部来源，不受阅读筛选影响。只复制星匣已有的数据。").small().color(MUTED));
                            }
                        });
                    }
                    if !self.message.is_empty() {
                        ui.add_space(12.0);
                        ui.label(&self.message);
                    }
                    if busy { ui.spinner(); }
                    ui.add_space(22.0);
                    ui.horizontal_wrapped(|ui| {
                        ui.label(RichText::new("按需整理").small().color(MUTED));
                        for (label, next) in [("存储空间", Action::Storage), ("图片与附件", Action::Resources), ("Skill 备份与恢复", Action::Skills)] {
                            if ui.add_enabled(!busy, egui::Button::new(label).frame(false)).clicked() { action = Some(next); }
                        }
                    });
                    ui.label(RichText::new("原应用记录保持不变。带走的是可检索阅读的档案；原客户端继续聊天的恢复方式另有要求。").small().color(MUTED));
                    ui.add_space(20.0);
                });
            });
        });
        action
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn older_preferences_start_with_chats_and_navigation_switches_with_a_click() {
        let prefs: crate::Preferences = serde_json::from_str("{}").unwrap();
        assert!(prefs.workspace == Workspace::Library);
        let ctx = egui::Context::default();
        let mut page = Workspace::Transfer;
        let mut position = egui::Pos2::ZERO;
        for frame in 0..3 {
            let output = ctx.run(
                egui::RawInput {
                    screen_rect: Some(egui::Rect::from_min_size(
                        egui::Pos2::ZERO,
                        egui::vec2(980.0, 640.0),
                    )),
                    events: if frame == 0 {
                        vec![]
                    } else {
                        vec![
                            egui::Event::PointerMoved(position),
                            egui::Event::PointerButton {
                                pos: position,
                                button: egui::PointerButton::Primary,
                                pressed: frame == 1,
                                modifiers: egui::Modifiers::NONE,
                            },
                        ]
                    },
                    ..Default::default()
                },
                |ctx| {
                    egui::CentralPanel::default().show(ctx, |ui| {
                        ui.horizontal(|ui| {
                            navigation(ui, &mut page);
                        });
                    });
                },
            );
            if frame == 0 {
                for shape in output.shapes {
                    if let egui::Shape::Text(text) = shape.shape {
                        if text.galley.text() == "聊天档案" {
                            position = text.pos + text.galley.size() * 0.5;
                        }
                    }
                }
                assert!(position != egui::Pos2::ZERO);
            }
        }
        assert!(page == Workspace::Library);
    }

    #[test]
    fn migration_steps_fit_regular_and_narrow_windows_without_reader_sidebars() {
        for width in [980.0, 1320.0] {
            let ctx = egui::Context::default();
            crate::setup(&ctx, 15.0);
            for _ in 0..3 {
                let output = ctx.run(
                    egui::RawInput {
                        screen_rect: Some(egui::Rect::from_min_size(
                            egui::Pos2::ZERO,
                            egui::vec2(width, 760.0),
                        )),
                        ..Default::default()
                    },
                    |ctx| {
                        egui::CentralPanel::default().show(ctx, |ui| {
                            let right = ui.max_rect().right();
                            assert_eq!(
                                State::default().show(
                                    ui,
                                    Path::new("/synthetic/archive"),
                                    &Catalog::default(),
                                    false,
                                    false
                                ),
                                None
                            );
                            assert!(
                                ui.min_rect().right() <= right + 1.0,
                                "content {:?}, available right {}",
                                ui.min_rect(),
                                right
                            );
                        });
                    },
                );
                let mut storage_visible = false;
                for shape in output.shapes {
                    if let egui::Shape::Text(text) = shape.shape {
                        assert!(
                            text.pos.x + text.galley.size().x <= width + 1.0,
                            "{}",
                            text.galley.text()
                        );
                        if text.galley.text() == "存储空间" {
                            storage_visible = true;
                            assert!(
                                text.pos.y + text.galley.size().y < 740.0,
                                "archive summary pushed storage below the window: {:?}",
                                text.pos
                            );
                        }
                    }
                }
                assert!(
                    storage_visible,
                    "storage entry must remain visible on the home page"
                );
            }
        }
    }

    #[test]
    fn export_requires_a_check_and_busy_actions_wait() {
        let catalog = Catalog {
            sessions: vec![crate::Session {
                meta: crate::SessionMeta {
                    id: "example".into(),
                    tool: "codex".into(),
                    ..Default::default()
                },
                display_title: "Example".into(),
                branch: "demo-codex".into(),
                device: "demo".into(),
                path: Default::default(),
                markdown: String::new(),
                search: String::new(),
            }],
            ..Default::default()
        };
        for (ready, busy, label, expected) in [
            (false, false, "检查档案并准备导出", Some(Action::Check)),
            (true, false, "选择位置并导出", Some(Action::Export)),
            (true, true, "选择位置并导出", None),
            (false, false, "选择来源并收集", Some(Action::Collect)),
            (false, false, "选择档案文件夹", Some(Action::Open)),
        ] {
            let ctx = egui::Context::default();
            crate::setup(&ctx, 15.0);
            let state = State { report: ready.then(|| serde_json::json!({"plan":true,"sessions":1,"files":3,"bytes":1000,"resources":0,"skills":0})), message: String::new() };
            let mut position = egui::Pos2::ZERO;
            let mut result = None;
            for frame in 0..3 {
                let output = ctx.run(
                    egui::RawInput {
                        screen_rect: Some(egui::Rect::from_min_size(
                            egui::Pos2::ZERO,
                            egui::vec2(1320.0, 860.0),
                        )),
                        events: if frame == 0 {
                            vec![]
                        } else {
                            vec![
                                egui::Event::PointerMoved(position),
                                egui::Event::PointerButton {
                                    pos: position,
                                    button: egui::PointerButton::Primary,
                                    pressed: frame == 1,
                                    modifiers: egui::Modifiers::NONE,
                                },
                            ]
                        },
                        ..Default::default()
                    },
                    |ctx| {
                        egui::CentralPanel::default().show(ctx, |ui| {
                            result = state.show(
                                ui,
                                Path::new("/synthetic/archive"),
                                &catalog,
                                busy,
                                false,
                            );
                        });
                    },
                );
                if frame == 0 {
                    for shape in output.shapes {
                        if let egui::Shape::Text(text) = shape.shape {
                            if text.galley.text() == label {
                                position = text.pos + text.galley.size() * 0.5;
                            }
                        }
                    }
                    assert!(position != egui::Pos2::ZERO, "button: {label}");
                }
                if frame < 2 {
                    assert_eq!(result, None);
                }
            }
            assert_eq!(result, expected, "button: {label}, busy: {busy}");
        }
    }
}
