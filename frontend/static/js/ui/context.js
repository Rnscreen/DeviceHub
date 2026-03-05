// js/ui/context.js - 右键菜单骨架
export class ContextMenu {
    constructor(app) {
        this.app = app;
        this.menu = document.getElementById('context-menu');
        this.currentBlock = null;
        this.setupContextMenu();
    }
    
    setupContextMenu() {
        document.addEventListener('contextmenu', (e) => {
            if (e.target.closest('.block') && this.app.isEditMode) {
                e.preventDefault();
                this.currentBlock = e.target.closest('.block');
                this.showMenu(e.pageX, e.pageY);
            }
        });
        
        document.addEventListener('click', () => {
            this.hideMenu();
        });
        
        this.menu?.addEventListener('click', (e) => {
            e.stopPropagation();
            const action = e.target.dataset.action;
            this.handleAction(action);
        });
    }
    
    showMenu(x, y) {
        if (!this.menu || !this.currentBlock) return;
        
        // 更新当前尺寸高亮
        const width = parseInt(this.currentBlock.getAttribute('data-width')) || 1;
        const height = parseInt(this.currentBlock.getAttribute('data-height')) || 1;
        
        this.menu.querySelectorAll('.context-item').forEach(item => {
            item.classList.remove('active');
            if (item.dataset.action === `resize-${width}x${height}`) {
                item.classList.add('active');
            }
        });
        
        this.menu.style.display = 'block';
        
        // 确保菜单位置
        const menuRect = this.menu.getBoundingClientRect();
        const finalX = x + menuRect.width > window.innerWidth ? x - menuRect.width : x;
        const finalY = y + menuRect.height > window.innerHeight ? y - menuRect.height : y;
        
        this.menu.style.left = `${finalX}px`;
        this.menu.style.top = `${finalY}px`;
    }
    
    hideMenu() {
        if (this.menu) {
            this.menu.style.display = 'none';
        }
    }
    
    handleAction(action) {
        if (!this.currentBlock) return;
        
        if (action === 'delete') {
            if (confirm('确定删除此控件？')) {
                this.currentBlock.remove();
                this.app.grid?.saveLayout();
            }
        } else if (action.startsWith('resize-')) {
            const [w, h] = action.replace('resize-', '').split('x').map(Number);
            this.currentBlock.setAttribute('data-width', w);
            this.currentBlock.setAttribute('data-height', h);
            
            if (this.app.grid) {
                this.app.grid.updateBlockSize(this.currentBlock, w, h);
                this.app.grid.saveLayout();
            }
        }
        
        this.hideMenu();
    }
}