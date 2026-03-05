// js/ui/grid.js
import { GRID_CONFIG, APP_CONFIG } from '../core/layout_config.js';
import { EventBus } from '../core/events.js';
import { debounce, isMobile } from '../core/utils.js';

export class GridManager {
    constructor(gridElement) {
        this.grid = gridElement;
        this.blocks = new Map();
        this.interact = null;
        this.events = new EventBus();
        
        this.currentBlock = null;
        this.isDragging = false;
        this.isResizing = false;
        
        this.init();
    }
    
    init() {
        this.setupGridStyles();
        this.initInteract();
        this.setupEventListeners();  // ✅ 先定义后调用
        this.loadLayout();
        
        // 响应式调整
        window.addEventListener('resize', debounce(() => this.handleResize(), 300));
    }
    
    setupEventListeners() {  // ✅ 添加这个方法定义
        // 这里可以添加网格特定的事件监听
        this.events.on('block:added', (data) => this.handleBlockAdded(data));
        this.events.on('block:removed', (data) => this.handleBlockRemoved(data));
    }
    
    handleBlockAdded(data) {
        console.log('块添加:', data);
        this.saveLayout();
    }
    
    handleBlockRemoved(data) {
        console.log('块移除:', data);
        this.saveLayout();
    }
    
    setupGridStyles() {
        // 设置网格Gap
        this.grid.style.gap = `${GRID_CONFIG.gap}px`;
    }
    
    initInteract() {
        if (typeof interact === 'undefined') {
            console.error('Interact.js not loaded');
            return;
        }
        
        // 重新初始化interact
        interact('.block').unset();
        
        // 拖拽配置
        interact('.block')
            .draggable({
                enabled: false,
                autoScroll: false,
                listeners: {
                    start: (event) => this.onDragStart(event),
                    move: (event) => this.onDragMove(event),
                    end: (event) => this.onDragEnd(event)
                }
            })
            .resizable({
                enabled: false,
                edges: { 
                    right: '.resize-handle', 
                    bottom: '.resize-handle' 
                },
                modifiers: [
                    interact.modifiers.snapSize({
                        targets: [
                            interact.snappers.grid({ 
                                x: GRID_CONFIG.cellWidth, 
                                y: GRID_CONFIG.cellHeight 
                            })
                        ]
                    })
                ],
                listeners: {
                    start: (event) => this.onResizeStart(event),
                    move: (event) => this.onResizeMove(event),
                    end: (event) => this.onResizeEnd(event)
                }
            });
    }
    
    onDragStart(event) {
        event.target.classList.add('dragging');
        this.isDragging = true;
        event.target.style.zIndex = '100';
        this.events.emit('block:drag-start', { block: event.target });
    }
    
    onDragMove(event) {
        if (isMobile()) return;
        
        const target = event.target;
        const rect = target.getBoundingClientRect();
        const gridRect = this.grid.getBoundingClientRect();
        
        // 计算网格位置
        const x = Math.round((rect.left - gridRect.left + event.dx) / GRID_CONFIG.cellWidth);
        const y = Math.round((rect.top - gridRect.top + event.dy) / GRID_CONFIG.cellHeight);
        
        // 限制边界
        const gridCols = this.getGridColumns();
        const blockWidth = parseInt(target.getAttribute('data-width')) || 1;
        const blockHeight = parseInt(target.getAttribute('data-height')) || 1;
        
        const maxX = gridCols - blockWidth;
        const maxY = 100;
        
        const finalX = Math.max(0, Math.min(x, maxX));
        const finalY = Math.max(0, Math.min(y, maxY));
        
        // 应用位置
        target.style.gridColumnStart = finalX + 1;
        target.style.gridColumnEnd = `span ${blockWidth}`;
        target.style.gridRowStart = finalY + 1;
        target.style.gridRowEnd = `span ${blockHeight}`;
        
        target.style.transform = 'none';
        
        this.events.emit('block:drag-move', { 
            block: target, 
            x: finalX, 
            y: finalY 
        });
    }
    
    onDragEnd(event) {
        event.target.classList.remove('dragging');
        event.target.style.zIndex = '';
        this.isDragging = false;
        
        this.saveLayout();
        this.events.emit('block:drag-end', { block: event.target });
    }
    
    onResizeStart(event) {
        event.target.classList.add('resizing');
        this.isResizing = true;
        event.target.style.zIndex = '100';
        this.events.emit('block:resize-start', { block: event.target });
    }
    
    onResizeMove(event) {
        const target = event.target;
        const width = event.rect.width;
        const height = event.rect.height;
        
        // 计算网格单位
        const cols = Math.max(1, Math.round(width / GRID_CONFIG.cellWidth));
        const rows = Math.max(1, Math.round(height / GRID_CONFIG.cellHeight));
        
        // 限制最大尺寸
        const maxCols = isMobile() ? 1 : APP_CONFIG.maxBlockWidth;
        const maxRows = isMobile() ? 1 : APP_CONFIG.maxBlockHeight;
        
        const finalCols = Math.min(cols, maxCols);
        const finalRows = Math.min(rows, maxRows);
        
        target.setAttribute('data-width', finalCols);
        target.setAttribute('data-height', finalRows);
        
        this.updateBlockSize(target, finalCols, finalRows);
        
        this.events.emit('block:resize-move', { 
            block: target, 
            width: finalCols, 
            height: finalRows 
        });
    }
    
    onResizeEnd(event) {
        event.target.classList.remove('resizing');
        event.target.style.zIndex = '';
        this.isResizing = false;
        
        this.saveLayout();
        this.events.emit('block:resize-end', { block: event.target });
    }
    
    updateBlockSize(block, cols, rows) {
        const currentColStart = parseInt(block.style.gridColumnStart) || 1;
        const gridCols = this.getGridColumns();
        
        if (currentColStart + cols - 1 > gridCols) {
            block.style.gridColumnStart = Math.max(1, gridCols - cols + 1);
        }
        
        block.style.gridColumnEnd = `span ${cols}`;
        block.style.gridRowEnd = `span ${rows}`;
    }
    
    getGridColumns() {
        const style = window.getComputedStyle(this.grid);
        return style.gridTemplateColumns.split(' ').length;
    }
    
    toggleEditMode(enable) {
        interact('.block').draggable({ enabled: enable });
        interact('.block').resizable({ enabled: enable });
        
        // 显示/隐藏调整手柄
        this.grid.querySelectorAll('.resize-handle').forEach(handle => {
            handle.style.display = enable ? 'block' : 'none';
        });
        
        this.events.emit('mode:change', { editMode: enable });
    }
    
    saveLayout() {
        if (this.isDragging || this.isResizing) return;
        
        const layout = [];
        this.grid.querySelectorAll('.block').forEach((block, index) => {
            layout.push({
                id: block.dataset.id || `block-${index}`,
                type: block.dataset.type || 'unknown',
                title: block.querySelector('.block-title')?.textContent || '',
                width: parseInt(block.getAttribute('data-width')) || 1,
                height: parseInt(block.getAttribute('data-height')) || 1,
                col: parseInt(block.style.gridColumnStart) || 1,
                row: parseInt(block.style.gridRowStart) || 1,
                config: block.dataset.config ? JSON.parse(block.dataset.config) : {}
            });
        });
        
        localStorage.setItem(APP_CONFIG.storageKey, JSON.stringify(layout));
        this.events.emit('layout:saved', { layout });
    }
    
    loadLayout() {
        const saved = localStorage.getItem(APP_CONFIG.storageKey);
        if (!saved) return;
        
        try {
            const layout = JSON.parse(saved);
            this.events.emit('layout:loading', { layout });
            
            // 这里会由BlocksManager处理实际的块创建
            this.events.emit('layout:restore', { layout });
            
        } catch (e) {
            console.error('加载布局失败:', e);
        }
    }
    
    getFirstEmptyPosition(width, height) {
        const gridCols = this.getGridColumns();
        const blocks = Array.from(this.grid.querySelectorAll('.block'));
        
        for (let row = 1; row <= 10; row++) {
            for (let col = 1; col <= gridCols - width + 1; col++) {
                let canPlace = true;
                
                for (const existing of blocks) {
                    const eCol = parseInt(existing.style.gridColumnStart) || 1;
                    const eRow = parseInt(existing.style.gridRowStart) || 1;
                    const eWidth = parseInt(existing.getAttribute('data-width')) || 1;
                    const eHeight = parseInt(existing.getAttribute('data-height')) || 1;
                    
                    if (col < eCol + eWidth && 
                        col + width > eCol &&
                        row < eRow + eHeight && 
                        row + height > eRow) {
                        canPlace = false;
                        break;
                    }
                }
                
                if (canPlace) {
                    return { col, row };
                }
            }
        }
        
        // 如果找不到空位，放在最后
        const lastRow = Math.max(...blocks.map(b => 
            (parseInt(b.style.gridRowStart) || 1) + (parseInt(b.getAttribute('data-height')) || 1) - 1
        ), 0);
        
        return { col: 1, row: lastRow + 1 };
    }
    
    handleResize() {
        this.events.emit('grid:resize');
        
        // 手机端强制调整块尺寸
        if (isMobile()) {
            this.grid.querySelectorAll('.block').forEach(block => {
                block.setAttribute('data-width', 1);
                block.setAttribute('data-height', 1);
                block.style.gridColumnStart = 1;
                block.style.gridColumnEnd = 'span 1';
            });
        }
        
        this.saveLayout();
    }
    
    destroy() {
        interact('.block').unset();
        window.removeEventListener('resize', this.handleResize);
    }
}