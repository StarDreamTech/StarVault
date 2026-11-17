//! Navigation uses confirmed identities within one source and archive branch.
use super::*;

#[derive(Clone, Default, Deserialize)]
#[serde(default)]
pub(super) struct Relation {
    pub kind: String,
    pub parent_id: String,
    pub agent_name: String,
    pub agent_type: String,
}

fn valid(session: &Session, relation: &Relation) -> bool {
    matches!(session.meta.tool.as_str(), "codex" | "claude")
        && matches!(relation.kind.as_str(), "subagent" | "fork")
        && !relation.parent_id.is_empty()
        && relation.parent_id != session.meta.id
}

fn same_source(a: &Session, b: &Session) -> bool {
    a.branch == b.branch && a.meta.tool == b.meta.tool
}

fn parent(catalog: &Catalog, selected: usize, relation: &Relation) -> Option<usize> {
    let session = &catalog.sessions[selected];
    valid(session, relation)
        .then(|| {
            catalog.sessions.iter().position(|other| {
                same_source(session, other) && other.meta.id == relation.parent_id
            })
        })
        .flatten()
}

fn children(catalog: &Catalog, selected: usize) -> Vec<(usize, &Relation)> {
    let session = &catalog.sessions[selected];
    catalog
        .sessions
        .iter()
        .enumerate()
        .flat_map(|(index, other)| {
            other
                .meta
                .session_relations
                .iter()
                .filter_map(move |relation| {
                    (same_source(session, other)
                        && valid(other, relation)
                        && relation.parent_id == session.meta.id)
                        .then_some((index, relation))
                })
        })
        .collect()
}

fn open_button(ui: &mut egui::Ui, title: &str) -> bool {
    ui.add(
        egui::Button::new(RichText::new(title).color(ACCENT))
            .frame(false)
            .truncate(),
    )
    .on_hover_text(title)
    .clicked()
}

pub(super) fn show(ui: &mut egui::Ui, catalog: &Catalog, selected: usize) -> Option<usize> {
    let session = &catalog.sessions[selected];
    let mut clicked = None;
    ui.push_id(
        ("session-relations", &session.branch, &session.meta.id),
        |ui| {
            for relation in session
                .meta
                .session_relations
                .iter()
                .filter(|r| valid(session, r))
            {
                let label = if relation.kind == "fork" {
                    "分叉自"
                } else {
                    "上级会话"
                };
                ui.horizontal(|ui| {
                    ui.label(RichText::new(label).small().color(MUTED));
                    if let Some(index) = parent(catalog, selected, relation) {
                        if open_button(ui, &catalog.sessions[index].display_title) {
                            clicked = Some(index);
                        }
                    } else {
                        ui.add(
                            egui::Label::new(
                                RichText::new("尚未导入上级会话").small().color(MUTED),
                            )
                            .truncate(),
                        )
                        .on_hover_text(&relation.parent_id);
                    }
                });
                if !relation.agent_type.is_empty() || !relation.agent_name.is_empty() {
                    let detail = [&relation.agent_type, &relation.agent_name]
                        .into_iter()
                        .filter(|v| !v.is_empty())
                        .map(String::as_str)
                        .collect::<Vec<_>>()
                        .join(" · ");
                    ui.add(
                        egui::Label::new(RichText::new(&detail).small().color(MUTED)).truncate(),
                    )
                    .on_hover_text(detail);
                }
            }
            let children = children(catalog, selected);
            if !children.is_empty() {
                egui::CollapsingHeader::new(format!("关联会话 · {}", children.len())).show(
                    ui,
                    |ui| {
                        egui::ScrollArea::vertical()
                            .max_height(160.0)
                            .show(ui, |ui| {
                                for (index, relation) in children {
                                    ui.horizontal(|ui| {
                                        ui.label(
                                            RichText::new(if relation.kind == "fork" {
                                                "分叉"
                                            } else {
                                                "子 Agent"
                                            })
                                            .small()
                                            .color(MUTED),
                                        );
                                        if open_button(ui, &catalog.sessions[index].display_title) {
                                            clicked = Some(index);
                                        }
                                    });
                                }
                            });
                    },
                );
            }
        },
    );
    clicked
}

#[cfg(test)]
mod tests {
    use super::*;

    fn session(branch: &str, tool: &str, id: &str, parent_id: &str) -> Session {
        Session {
            meta: SessionMeta {
                id: id.into(),
                tool: tool.into(),
                session_relations: if parent_id.is_empty() {
                    vec![]
                } else {
                    vec![Relation {
                        kind: "subagent".into(),
                        parent_id: parent_id.into(),
                        ..Default::default()
                    }]
                },
                ..Default::default()
            },
            display_title: format!("会话 {id}"),
            branch: branch.into(),
            device: String::new(),
            path: PathBuf::new(),
            markdown: String::new(),
            search: String::new(),
        }
    }

    #[test]
    fn relationships_stay_with_their_source_and_computer() {
        let catalog = Catalog {
            sessions: vec![
                session("mac-codex", "codex", "parent", ""),
                session("mac-codex", "codex", "child", "parent"),
                session("other-codex", "codex", "child", "parent"),
                session("mac-claude", "claude", "parent", ""),
                session("mac-codex", "claude", "wrong-source", "parent"),
                session("mac-codex", "codex", "self", "self"),
            ],
            ..Default::default()
        };
        assert_eq!(
            children(&catalog, 0)
                .iter()
                .map(|(i, _)| *i)
                .collect::<Vec<_>>(),
            vec![1]
        );
        assert_eq!(
            parent(&catalog, 1, &catalog.sessions[1].meta.session_relations[0]),
            Some(0)
        );
        assert_eq!(
            parent(&catalog, 2, &catalog.sessions[2].meta.session_relations[0]),
            None
        );
        assert!(children(&catalog, 5).is_empty());
    }

    #[test]
    fn parent_button_opens_an_existing_session() {
        let ctx = egui::Context::default();
        let catalog = Catalog {
            sessions: vec![
                session("mac-codex", "codex", "parent", ""),
                session("mac-codex", "codex", "child", "parent"),
            ],
            ..Default::default()
        };
        let mut button = None;
        let mut target = None;
        for frame in 0..3 {
            let mut input = egui::RawInput {
                screen_rect: Some(egui::Rect::from_min_size(
                    egui::Pos2::ZERO,
                    egui::vec2(400.0, 220.0),
                )),
                ..Default::default()
            };
            if let Some(at) = button {
                input.events = vec![
                    egui::Event::PointerMoved(at),
                    egui::Event::PointerButton {
                        pos: at,
                        button: egui::PointerButton::Primary,
                        pressed: frame == 1,
                        modifiers: egui::Modifiers::NONE,
                    },
                ];
            }
            let output = ctx.run(input, |ctx| {
                egui::CentralPanel::default().show(ctx, |ui| {
                    target = show(ui, &catalog, 1).or(target);
                });
            });
            if frame == 0 {
                button = output.shapes.iter().find_map(|shape| match &shape.shape {
                    egui::epaint::Shape::Text(text) if text.galley.text() == "会话 parent" => {
                        Some(text.pos + text.galley.size() * 0.5)
                    }
                    _ => None,
                });
                assert!(button.is_some());
            }
        }
        assert_eq!(target, Some(0));
    }

    #[test]
    fn long_parent_titles_fit_a_narrow_reader_and_missing_parents_stay_readable() {
        let ctx = egui::Context::default();
        let mut catalog = Catalog {
            sessions: vec![
                session("mac-codex", "codex", "parent", ""),
                session("mac-codex", "codex", "child", "parent"),
            ],
            ..Default::default()
        };
        catalog.sessions[0].display_title = "很长的主会话标题".repeat(300);
        for missing in [false, true] {
            if missing {
                catalog.sessions[1].meta.session_relations[0].parent_id = "missing".into();
            }
            let _ = ctx.run(
                egui::RawInput {
                    screen_rect: Some(egui::Rect::from_min_size(
                        egui::Pos2::ZERO,
                        egui::vec2(320.0, 220.0),
                    )),
                    ..Default::default()
                },
                |ctx| {
                    egui::CentralPanel::default().show(ctx, |ui| {
                        let right = ui.max_rect().right();
                        assert_eq!(show(ui, &catalog, 1), None);
                        assert!(ui.min_rect().right() <= right + 1.0);
                    });
                },
            );
        }
    }
}
