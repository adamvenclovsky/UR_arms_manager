# Current architecture

## 1. Project state
- backend core implemented
- CLI implemented
- GUI stage planned next

## 2. Core architectural principles
- lightweight Python-first system
- no mandatory ROS 2
- small diffs
- service-oriented backend core
- operator-friendly interfaces

## 3. Current layers
### domain/models
### registry/config
### adapters
- dashboard
- script socket
- SSH/SFTP file access

### services
- robot manager
- library manager
- compatibility service
- URP analysis/update support

### interfaces
- CLI
- upcoming GUI/API layer

## 4. Program models
- remote `.urp`
- library-managed `.urp`
- library-managed `.script`
- imported robot-side files

## 5. Runtime distinctions
- dashboard-visible program paths
- raw SSH filesystem paths
- direct `.script` execution path

## 6. Library model
- storage/programs/<program_id>/
- manifest.yaml
- origin metadata
- inspect / compatibility / params

## 7. URP handling policy
- read-only analysis by default
- very limited safe param editing only
- no generic raw editor

## 8. URSim Docker notes
- custom image with SSH
- observed file paths
- dashboard load path differences

## 9. Planned GUI architecture
- FastAPI
- Jinja2
- HTMX
- lightweight polling
- reuse backend services

## 10. Deferred items
- ROS 2 bridge optional
- RTDE revisit if needed
- no heavy desktop framework by default