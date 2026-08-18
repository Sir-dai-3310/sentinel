# Governance Model

## Overview

Sentinel follows a **benevolent dictator** governance model during its early stages, transitioning to a **meritocratic committee** model as the community grows.

## Roles

### Core Team
- **Responsibilities**: Final decision authority, roadmap direction, release management, security response
- **Selection**: Initial core team members are the project founders
- **Size**: 3-5 members

### Maintainers
- **Responsibilities**: Code review, issue triage, documentation, community support
- **Selection**: Nominated by core team based on sustained contributions (10+ merged PRs over 3+ months)
- **Powers**: Can approve and merge PRs, close issues, manage labels

### Contributors
- **Responsibilities**: Submit PRs, report bugs, suggest features, help other users
- **Selection**: Anyone who has contributed at least 1 merged PR
- **Powers**: Can submit PRs, participate in discussions

### Community Members
- **Responsibilities**: Use the software, provide feedback, participate in discussions
- **Selection**: Anyone using or interested in Sentinel

## Decision Making

### Routine Decisions
- Bug fixes, documentation updates, minor improvements → **Lazy consensus** (silence = agreement after 72 hours)

### Significant Decisions
- New features, API changes, architectural changes → **RFC process** (see below)

### Major Decisions
- License changes, governance model changes, project direction → **Core team vote** (2/3 majority required)

## RFC Process

For significant changes, create an RFC (Request for Comments):

1. **Draft**: Write a proposal in `rfcs/NNNN-title.md`
2. **Discussion**: Open a GitHub Discussion for community feedback (minimum 7 days)
3. **Review**: Core team reviews and provides feedback
4. **Decision**: Core team accepts or rejects with explanation
5. **Implementation**: Approved RFCs are implemented by the proposer or assigned to a maintainer

## Conflict Resolution

1. **Direct discussion**: Try to resolve conflicts through respectful dialogue
2. **Mediation**: Ask a maintainer to mediate
3. **Escalation**: Core team makes final decision
4. **Code of Conduct**: Violations are handled per CODE_OF_CONDUCT.md

## Release Process

1. **Feature freeze**: 2 weeks before release
2. **Release candidate**: 1 week of testing
3. **Final release**: Core team approval
4. **Post-release**: Monitor for regressions, hotfix if needed

## Communication Channels

- **GitHub Issues**: Bug reports, feature requests
- **GitHub Discussions**: General questions, RFCs, community discussion
- **GitHub PRs**: Code contributions
- **Discord** (planned): Real-time chat, community support
