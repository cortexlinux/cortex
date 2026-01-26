//! CX Terminal: Create new projects from templates
use clap::Parser;

#[derive(Debug, Parser, Clone)]
pub struct NewCommand {
    /// The template to use (e.g., "rust", "python", "node")
    #[arg(default_value = "default")]
    pub template: String,

    /// The name of the new project
    #[arg(short, long)]
    pub name: Option<String>,

    /// The directory to create the project in
    #[arg(short, long)]
    pub dir: Option<String>,
}

impl NewCommand {
    pub fn run(&self) -> anyhow::Result<()> {
        eprintln!(
            "CX Terminal: 'new' command is not yet implemented. Template: {}",
            self.template
        );
        eprintln!("This feature will create new projects from templates.");
        Ok(())
    }
}
