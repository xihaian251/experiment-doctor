"""Synthetic stand-in for TorchSSL's models/fixmatch/fixmatch.py training loop."""
class FixMatch:
    def train(self):
        best_eval_acc, best_it = 0.0, 0
        for (_, x_lb, y_lb), _ in zip(self.loader_dict['train_lb'], self.loader_dict['train_ulb']):
            # prevent the training iterations exceed args.num_train_iter
            if self.it > args.num_train_iter:
                break
            if self.it % self.num_eval_iter == 0:
                tb_dict = self.validate()
                if tb_dict['eval/top-1-acc'] > best_eval_acc:
                    best_eval_acc = tb_dict['eval/top-1-acc']
                    best_it = self.it
                log(f"{self.it} iteration, {tb_dict}, BEST_EVAL_ACC: {best_eval_acc}, at {best_it} iters")
            self.it += 1
            if self.it > 0.8 * args.num_train_iter:
                self.num_eval_iter = 1000
        return best_eval_acc
